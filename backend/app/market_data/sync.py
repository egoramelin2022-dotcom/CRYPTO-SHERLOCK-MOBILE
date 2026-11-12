"""Resumable, bounded Binance Spot historical candle synchronization.

This module performs ingestion only. It never places orders and never
fabricates candles. Empty source responses stop the job visibly rather than
being interpreted as proof that the requested range is complete.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from random import random
from typing import Callable

import httpx

from .binance import parse_binance_kline
from .candles import Candle
from .intervals import interval_to_ms
from .repository import CandleRepository
from .gap_registry import ensure_gap_registry, record_gap

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_MAX_LIMIT = 1000
RETRYABLE_STATUS = {418, 429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class SyncResult:
    status: str
    fetched: int
    inserted: int
    next_start_ms: int
    pages: int


def ensure_sync_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sync_jobs (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            requested_start_ms INTEGER NOT NULL,
            requested_end_ms INTEGER NOT NULL,
            next_start_ms INTEGER NOT NULL,
            status TEXT NOT NULL,
            fetched INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0,
            pages INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            last_error TEXT,
            PRIMARY KEY(symbol, interval, requested_start_ms, requested_end_ms)
        )"""
    )
    conn.commit()


class HistoricalSyncEngine:
    """Download closed, fixed-interval Binance Spot candles with checkpoints."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        client: httpx.Client | None = None,
        max_attempts: int = 5,
        backoff_base_seconds: float = 0.5,
        backoff_cap_seconds: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random,
    ) -> None:
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if backoff_base_seconds < 0 or backoff_cap_seconds < 0:
            raise ValueError("backoff values must be nonnegative")
        self.connection = connection
        self.client = client or httpx.Client(timeout=httpx.Timeout(
            connect=5.0, read=20.0, write=10.0, pool=5.0
        ))
        self._owns_client = client is None
        self.max_attempts = max_attempts
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_cap_seconds = backoff_cap_seconds
        self.sleep = sleep
        self.jitter = jitter
        self.repository = CandleRepository(connection)
        self.repository.ensure_schema()
        ensure_sync_schema(connection)
        ensure_gap_registry(connection)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "HistoricalSyncEngine":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _checkpoint(
        self, symbol: str, interval: str, start_ms: int, end_ms: int,
        next_start_ms: int, status: str, fetched: int, inserted: int,
        pages: int, error: str | None = None,
    ) -> None:
        updated = datetime.now(timezone.utc).isoformat()
        with self.connection:
            self.connection.execute(
                """INSERT INTO sync_jobs (
                    symbol, interval, requested_start_ms, requested_end_ms,
                    next_start_ms, status, fetched, inserted, pages,
                    updated_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval, requested_start_ms, requested_end_ms)
                DO UPDATE SET next_start_ms=excluded.next_start_ms,
                    status=excluded.status, fetched=excluded.fetched,
                    inserted=excluded.inserted, pages=excluded.pages,
                    updated_at=excluded.updated_at, last_error=excluded.last_error""",
                (symbol, interval, start_ms, end_ms, next_start_ms, status,
                 fetched, inserted, pages, updated, error),
            )

    def _request_page(self, params: dict[str, int | str]) -> list:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.get(BINANCE_KLINES_URL, params=params)
                if response.status_code in RETRYABLE_STATUS:
                    if attempt + 1 == self.max_attempts:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = self._retry_delay(attempt, retry_after)
                    self.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("Binance klines response must be a JSON array")
                return payload
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt + 1 == self.max_attempts:
                    raise
                self.sleep(self._retry_delay(attempt, None))
            except httpx.HTTPStatusError:
                raise
        if last_error:
            raise last_error
        raise RuntimeError("request retry loop ended unexpectedly")

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                requested = max(0.0, float(retry_after))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(retry_after)
                    requested = max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    requested = 0.0
            if requested > 0:
                return min(requested, self.backoff_cap_seconds)
        exponential = self.backoff_base_seconds * (2 ** attempt)
        return min(exponential * (0.5 + self.jitter()), self.backoff_cap_seconds)

    def sync(
        self, *, symbol: str, interval: str, start_ms: int, end_ms: int,
        page_limit: int = BINANCE_MAX_LIMIT, resume: bool = True,
    ) -> SyncResult:
        step = interval_to_ms(interval)
        if not isinstance(symbol, str) or not symbol or not symbol.isalnum():
            raise ValueError("invalid symbol")
        for name, value in (("start_ms", start_ms), ("end_ms", end_ms)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
            if value % step:
                raise ValueError(f"{name} must align to interval")
        if start_ms > end_ms:
            raise ValueError("start_ms must be <= end_ms")
        if isinstance(page_limit, bool) or not isinstance(page_limit, int) or not 1 <= page_limit <= BINANCE_MAX_LIMIT:
            raise ValueError("page_limit must be between 1 and 1000")

        row = self.connection.execute(
            """SELECT next_start_ms, status, fetched, inserted, pages
               FROM sync_jobs WHERE symbol=? AND interval=?
               AND requested_start_ms=? AND requested_end_ms=?""",
            (symbol, interval, start_ms, end_ms),
        ).fetchone()
        if row and resume and row[1] == "COMPLETE":
            return SyncResult(
                "COMPLETE", int(row[2]), int(row[3]), int(row[0]), int(row[4])
            )
        if row and resume and row[1] in {"RUNNING", "SOURCE_EMPTY", "FAILED"}:
            cursor, fetched, inserted, pages = int(row[0]), int(row[2]), int(row[3]), int(row[4])
        else:
            # PARTIAL jobs are deliberately rescanned from the requested start:
            # idempotent inserts preserve existing rows while rechecking holes.
            cursor, fetched, inserted, pages = start_ms, 0, 0, 0

        if cursor > end_ms:
            self._checkpoint(symbol, interval, start_ms, end_ms, cursor,
                             "COMPLETE", fetched, inserted, pages)
            return SyncResult("COMPLETE", fetched, inserted, cursor, pages)

        self._checkpoint(symbol, interval, start_ms, end_ms, cursor,
                         "RUNNING", fetched, inserted, pages)
        has_gaps = False
        previous_time_row = self.connection.execute(
            """SELECT MAX(open_time) FROM candles
               WHERE symbol=? AND interval=? AND open_time >= ? AND open_time < ?""",
            (symbol, interval, start_ms, cursor),
        ).fetchone()
        previous_time = (
            int(previous_time_row[0]) if previous_time_row and previous_time_row[0] is not None
            else None
        )
        while cursor <= end_ms:
            try:
                payload = self._request_page({
                    "symbol": symbol, "interval": interval,
                    "startTime": cursor, "endTime": end_ms, "limit": page_limit,
                })
                if not payload:
                    if previous_time is not None and previous_time < end_ms:
                        missing = (end_ms - previous_time) // step
                        if missing > 0:
                            record_gap(
                                self.connection, symbol=symbol, interval=interval,
                                previous_open_time=previous_time,
                                next_open_time=end_ms + step,
                                missing_candles=missing, status="GAP_DETECTED",
                                source="BINANCE_SPOT_REST",
                                details="Source returned an empty page before requested range ended",
                            )
                    self._checkpoint(symbol, interval, start_ms, end_ms, cursor,
                                     "SOURCE_EMPTY", fetched, inserted, pages,
                                     "Binance returned an empty page before requested end")
                    return SyncResult("SOURCE_EMPTY", fetched, inserted, cursor, pages)
                if len(payload) > page_limit:
                    raise ValueError("Binance page exceeds requested limit")

                candles: list[Candle] = [
                    parse_binance_kline(item, symbol=symbol, interval=interval)
                    for item in payload
                ]
                times = [c.open_time for c in candles]
                if times != sorted(set(times)):
                    raise ValueError("Binance page timestamps must be strictly increasing")
                if times[0] < cursor or times[-1] > end_ms:
                    raise ValueError("Binance page contains timestamps outside requested bounds")

                # Audit every discontinuity, including the leading edge of a
                # requested range and the boundary between consecutive pages.
                expected_previous = previous_time if previous_time is not None else cursor - step
                first_time = times[0]
                if first_time > expected_previous + step:
                    missing = (first_time - expected_previous) // step - 1
                    record_gap(
                        self.connection, symbol=symbol, interval=interval,
                        previous_open_time=expected_previous,
                        next_open_time=first_time, missing_candles=missing,
                        status="GAP_DETECTED", source="BINANCE_SPOT_REST",
                        details="Missing interval detected while ingesting a non-empty page",
                    )
                    has_gaps = True
                for left, right in zip(times, times[1:]):
                    if right - left > step:
                        missing = (right - left) // step - 1
                        record_gap(
                            self.connection, symbol=symbol, interval=interval,
                            previous_open_time=left, next_open_time=right,
                            missing_candles=missing, status="GAP_DETECTED",
                            source="BINANCE_SPOT_REST",
                            details="Internal discontinuity inside Binance response page",
                        )
                        has_gaps = True

                new_cursor = times[-1] + step
                if new_cursor <= cursor:
                    raise ValueError("Binance page did not advance the synchronization cursor")

                # Candle transaction commits first. If the process stops before
                # the checkpoint, a resumed request is safe because inserts are idempotent.
                inserted_now = self.repository.insert_many(candles)
                fetched += len(candles)
                inserted += inserted_now
                pages += 1
                cursor = new_cursor
                previous_time = times[-1]
                self._checkpoint(
                    symbol, interval, start_ms, end_ms, cursor, "RUNNING",
                    fetched, inserted, pages,
                )
            except Exception as exc:
                self._checkpoint(
                    symbol, interval, start_ms, end_ms, cursor, "FAILED",
                    fetched, inserted, pages, f"{type(exc).__name__}: {exc}",
                )
                raise

        # A page can end before the requested range. Record the trailing
        # uncovered slots explicitly; never label a sparse range complete.
        if previous_time is not None and previous_time < end_ms:
            missing = (end_ms - previous_time) // step
            if missing > 0:
                record_gap(
                    self.connection, symbol=symbol, interval=interval,
                    previous_open_time=previous_time,
                    next_open_time=end_ms + step,
                    missing_candles=missing, status="GAP_DETECTED",
                    source="BINANCE_SPOT_REST",
                    details="Requested range ended before the final expected candle arrived",
                )
                has_gaps = True

        final_status = "PARTIAL" if has_gaps else "COMPLETE"
        self._checkpoint(symbol, interval, start_ms, end_ms, cursor,
                         final_status, fetched, inserted, pages,
                         "One or more candle intervals are missing" if has_gaps else None)
        return SyncResult(final_status, fetched, inserted, cursor, pages)
