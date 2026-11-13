"""Historical Binance archive download job for the desktop data center."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.market_data.intervals import floor_to_interval, interval_to_ms
from app.market_data.sync import HistoricalSyncEngine
from app.research import jobs as base_jobs
from scripts.download_binance_spot_klines import run as download_archives


def _record_progress(job_id: str, message: str) -> None:
    current = base_jobs.get_job(job_id) or {}
    previous = (current.get("result") or {}).get("progress_log", [])
    progress_log = [*previous, message][-200:]
    base_jobs._set_job(
        job_id,
        result={"progress": message[-500:], "progress_log": progress_log},
    )


def run_archive_download(job_id: str, start: str, end: str) -> None:
    base_jobs._set_job(job_id, status="running", result={"progress": "Preparing staging download"})
    try:
        root = Path(__file__).resolve().parents[3]
        raw_dir = Path(os.getenv(
            "SHERLOCK_ARCHIVE_RAW_DIR", str(root / "data" / "binance_public_raw")
        )).expanduser().resolve()
        db_path = Path(os.getenv(
            "SHERLOCK_ARCHIVE_STAGING_DB", str(root / "data" / "binance_archive_staging.db")
        )).expanduser().resolve()
        source, analytics = base_jobs._configured_paths()
        if db_path in (source, analytics):
            raise RuntimeError("Archive staging database must be separate from source and analytics databases")
        inserted = download_archives(
            start, end, raw_dir, db_path,
            progress_callback=lambda message: _record_progress(job_id, message),
        )
        base_jobs._set_job(job_id, status="completed", result={
            "inserted_this_run": inserted,
            "staging_database": str(db_path),
            "raw_archive_cache": str(raw_dir),
            "progress_log": (base_jobs.get_job(job_id) or {}).get("result", {}).get("progress_log", []),
            "note": "Staging only. Source market database was not modified.",
        })
    except Exception as exc:
        base_jobs._set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")



def run_recent_sync_job(
    job_id: str, symbol: str = "BTCUSDT", *, now: datetime | None = None
) -> None:
    """Sync the current UTC month of closed candles into isolated staging storage."""
    base_jobs._set_job(job_id, status="running", result={
        "progress": "Preparing current-month public Binance Spot sync"
    })
    try:
        root = Path(__file__).resolve().parents[3]
        staging_path = Path(os.getenv(
            "SHERLOCK_ARCHIVE_STAGING_DB",
            str(root / "data" / "binance_archive_staging.db"),
        )).expanduser().resolve()
        source_path, analytics_path = base_jobs._configured_paths()
        if staging_path in (source_path, analytics_path):
            raise RuntimeError(
                "Recent sync staging database must be separate from source and analytics databases"
            )
        staging_path.parent.mkdir(parents=True, exist_ok=True)

        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("sync reference time must be timezone-aware")
        now = now.astimezone(timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start_ms = int(month_start.timestamp() * 1000)
        results = {}
        connection = sqlite3.connect(staging_path)
        try:
            with HistoricalSyncEngine(connection) as engine:
                for interval in ("15m", "4h", "1d"):
                    step = interval_to_ms(interval)
                    start_ms = floor_to_interval(month_start_ms, interval)
                    end_ms = floor_to_interval(now_ms, interval) - step
                    if end_ms < start_ms:
                        results[interval] = {
                            "status": "NO_CLOSED_CANDLES",
                            "fetched": 0, "inserted": 0, "pages": 0,
                        }
                        continue
                    result = engine.sync(
                        symbol=symbol, interval=interval,
                        start_ms=start_ms, end_ms=end_ms, resume=True,
                    )
                    results[interval] = asdict(result)
                    _record_progress(
                        job_id,
                        f"{interval}: {result.status}; fetched={result.fetched}; "
                        f"inserted={result.inserted}; pages={result.pages}",
                    )
        finally:
            connection.close()

        status = (
            "completed" if all(
                item["status"] in {"COMPLETE", "NO_CLOSED_CANDLES"}
                for item in results.values()
            ) else "failed"
        )
        base_jobs._set_job(job_id, status=status, result={
            "symbol": symbol,
            "intervals": results,
            "staging_database": str(staging_path),
            "as_of_utc": now.isoformat(),
            "note": (
                "Current UTC month only; closed candles only. Data is written to "
                "archive staging, never to the source market database."
            ),
        }, error=None if status == "completed" else "One or more intervals remain partial; inspect results and retry.")
    except Exception as exc:
        base_jobs._set_job(
            job_id, status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )
