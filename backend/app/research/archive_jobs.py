"""Historical Binance archive download job for the desktop data center."""
from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from app.research import jobs as base_jobs
from scripts.download_binance_spot_klines import run as download_archives


class _ProgressWriter(io.StringIO):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        self.pending = ""

    def write(self, value: str) -> int:
        count = super().write(value)
        self.pending += value
        if "\n" in self.pending:
            lines = self.pending.splitlines()
            self.pending = self.pending.rsplit("\n", 1)[-1]
            if lines:
                base_jobs._set_job(
                    self.job_id, result={"progress": lines[-1][-500:]}
                )
        return count


def run_archive_download(job_id: str, start: str, end: str) -> None:
    base_jobs._set_job(job_id, status="running", result={"progress": "Preparing staging download"})
    try:
        root = Path(__file__).resolve().parents[2]
        raw_dir = Path(os.getenv(
            "SHERLOCK_ARCHIVE_RAW_DIR", str(root / "data" / "binance_public_raw")
        )).expanduser().resolve()
        db_path = Path(os.getenv(
            "SHERLOCK_ARCHIVE_STAGING_DB", str(root / "data" / "binance_archive_staging.db")
        )).expanduser().resolve()
        source, analytics = base_jobs._configured_paths()
        if db_path in (source, analytics):
            raise RuntimeError("Archive staging database must be separate from source and analytics databases")
        writer = _ProgressWriter(job_id)
        with redirect_stdout(writer):
            inserted = download_archives(start, end, raw_dir, db_path)
        base_jobs._set_job(job_id, status="completed", result={
            "inserted_this_run": inserted,
            "staging_database": str(db_path),
            "raw_archive_cache": str(raw_dir),
            "progress_log": writer.getvalue()[-12000:],
            "note": "Staging only. Source market database was not modified.",
        })
    except Exception as exc:
        base_jobs._set_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
