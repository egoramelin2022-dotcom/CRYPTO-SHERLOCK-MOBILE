"""Local research job runner for the read-only Sherlock data foundation.

Jobs execute in FastAPI's background thread pool. Job state is process-local;
the derived analytics database remains the durable output of pipeline runs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
import os

from app.market_data.pipeline import run_historical_pipeline
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
