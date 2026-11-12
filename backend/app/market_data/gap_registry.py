"""Persistent gap registry; observations never imply missing candles are zero."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

GAP_STATUSES = {
    "GAP_DETECTED",
    "SOURCE_EMPTY",
    "SOURCE_ERROR",
    "RECOVERED",
    "UNRESOLVED",
}


def ensure_gap_registry(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS data_gaps (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            previous_open_time INTEGER NOT NULL,
            next_open_time INTEGER NOT NULL,
            missing_candles INTEGER NOT NULL CHECK(missing_candles > 0),
            status TEXT NOT NULL CHECK(status IN (
                'GAP_DETECTED','SOURCE_EMPTY','SOURCE_ERROR','RECOVERED','UNRESOLVED'
            )),
            source TEXT,
            checked_at TEXT NOT NULL,
            details TEXT,
            PRIMARY KEY(symbol, interval, previous_open_time, next_open_time)
        )"""
    )
    conn.commit()


def record_gap(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    interval: str,
    previous_open_time: int,
    next_open_time: int,
    missing_candles: int,
    status: str = "GAP_DETECTED",
    source: str | None = None,
    details: str | None = None,
) -> None:
    if status not in GAP_STATUSES:
        raise ValueError(f"unsupported gap status: {status}")
    if missing_candles <= 0 or next_open_time <= previous_open_time:
        raise ValueError("invalid gap bounds or missing candle count")
    ensure_gap_registry(conn)
    checked_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO data_gaps (
            symbol, interval, previous_open_time, next_open_time,
            missing_candles, status, source, checked_at, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, interval, previous_open_time, next_open_time)
        DO UPDATE SET missing_candles=excluded.missing_candles,
            status=excluded.status, source=excluded.source,
            checked_at=excluded.checked_at, details=excluded.details""",
        (symbol, interval, previous_open_time, next_open_time,
         missing_candles, status, source, checked_at, details),
    )
    conn.commit()
