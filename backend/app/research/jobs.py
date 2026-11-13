"""Local research job runner for the read-only Sherlock data foundation.

Jobs execute in FastAPI's background thread pool. Job state is process-local;
the derived analytics database remains the durable output of pipeline runs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
import os

from app.market_data.pipeline import load_candles_read_only, run_historical_pipeline
from app.market_data.intervals import interval_to_ms
from app.research.ensemble_pipeline import run_ensemble_search
from app.research.data_foundation import audit_sqlite_dataset


@dataclass
class Job:
    job_id: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


_jobs: dict[str, Job] = {}
_lock = Lock()
_pipeline_lock = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job(kind: str) -> Job:
    now = _now()
    job = Job(str(uuid4()), kind, "queued", now, now)
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return asdict(job) if job else None


def _set_job(job_id: str, **changes: Any) -> None:
    with _lock:
        job = _jobs[job_id]
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = _now()


def _configured_paths() -> tuple[Path, Path]:
    source = os.getenv("SHERLOCK_SOURCE_DB")
    analytics = os.getenv("SHERLOCK_ANALYTICS_DB")
    if not source or not analytics:
        raise RuntimeError(
            "Configure SHERLOCK_SOURCE_DB and SHERLOCK_ANALYTICS_DB on the server"
        )
    source_path = Path(source).expanduser().resolve()
    analytics_path = Path(analytics).expanduser().resolve()
    if source_path == analytics_path:
        raise RuntimeError("Analytics database must be separate from the source database")
    if not source_path.is_file():
        raise FileNotFoundError(f"Configured source database does not exist: {source_path}")
    return source_path, analytics_path


def queue_audit() -> dict[str, Any]:
    return asdict(_new_job("data_audit"))


def run_audit_job(job_id: str) -> None:
    _set_job(job_id, status="running")
    try:
        source, _ = _configured_paths()
        result = audit_sqlite_dataset(source)
        _set_job(job_id, status="completed", result=result)
    except Exception as exc:
        _set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")


def queue_pipeline() -> dict[str, Any]:
    return asdict(_new_job("historical_pipeline"))


def run_pipeline_job(job_id: str, symbol: str, interval: str, window: int) -> None:
    _set_job(job_id, status="running")
    try:
        source, analytics = _configured_paths()
        # The analytics SQLite file is shared. Serialize writers so two
        # background jobs cannot interleave schema creation and transactions.
        with _pipeline_lock:
            result = run_historical_pipeline(
                source, analytics, symbol=symbol, interval=interval, window=window
            )
        _set_job(job_id, status="completed", result=asdict(result))
    except Exception as exc:
        _set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")



def queue_ensemble() -> dict[str, Any]:
    return asdict(_new_job("ensemble_research"))


def _latest_contiguous_segment(candles, interval: str):
    """Return the latest gap-free segment without filling missing candles."""
    step = interval_to_ms(interval)
    segments = []
    current = []
    previous = None
    for candle in candles:
        if previous is not None and candle.open_time - previous != step:
            if current:
                segments.append(current)
            current = []
        current.append(candle)
        previous = candle.open_time
    if current:
        segments.append(current)
    if not segments:
        return [], 0, 0
    latest = segments[-1]
    return latest, len(segments), len(candles) - len(latest)


def run_ensemble_job(
    job_id: str,
    symbol: str,
    interval: str,
    window: int,
    top_k: int = 10,
    mode: str = "free",
    include_stumpy: bool = False,
) -> None:
    """Run read-only ensemble research and persist only to analytics SQLite."""
    _set_job(job_id, status="running")
    try:
        source, analytics = _configured_paths()
        all_candles = load_candles_read_only(
            source, symbol=symbol, interval=interval,
        )
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        closed = [c for c in all_candles if c.close_time < now_ms]
        segment, segment_count, excluded = _latest_contiguous_segment(
            closed, interval,
        )
        if len(segment) < window:
            raise ValueError(
                f"latest contiguous closed segment has {len(segment)} candles; "
                f"{window} are required for the query window"
            )

        run = run_ensemble_search(
            segment,
            query_start_index=len(segment) - window,
            query_end_index=len(segment) - 1,
            mode=mode,
            top_k=top_k,
            include_stumpy=include_stumpy,
        )
        run_id = str(uuid4())
        result = {
            "run_id": run_id,
            "source_candles_read": len(all_candles),
            "closed_candles": len(closed),
            "contiguous_segments": segment_count,
            "candles_excluded_before_latest_segment": excluded,
            "active_segment_start_time": segment[0].open_time,
            "active_segment_end_time": segment[-1].open_time,
            "run": run.to_dict(),
            "limitations": [
                "Only the latest contiguous segment is searched; earlier segments are not bridged across data gaps.",
                "Source SQLite was opened read-only. Only the separate analytics database receives this run record.",
                "Only closed candles are included. No gap filling or interpolation is performed.",
            ],
        }

        analytics.parent.mkdir(parents=True, exist_ok=True)
        with _pipeline_lock:
            connection = sqlite3.connect(str(analytics))
            try:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS research_ensemble_runs (
                        run_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        interval TEXT NOT NULL,
                        query_start_time INTEGER NOT NULL,
                        query_end_time INTEGER NOT NULL,
                        mode TEXT NOT NULL,
                        include_stumpy INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        result_json TEXT NOT NULL
                    )"""
                )
                with connection:
                    connection.execute(
                        """INSERT INTO research_ensemble_runs VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )""",
                        (
                            run_id, symbol, interval,
                            run.query_start_time, run.query_end_time,
                            mode, int(include_stumpy), _now(),
                            json.dumps(result, separators=(",", ":"), sort_keys=True),
                        ),
                    )
            finally:
                connection.close()
        _set_job(job_id, status="completed", result=result)
    except Exception as exc:
        _set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
