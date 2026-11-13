"""Embedded loopback-only FastAPI backend for the standalone desktop app."""
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal


class EmbeddedBackend(QThread):
    failed = Signal(str)

    def __init__(self, source_db: Path, analytics_db: Path):
        super().__init__()
        self.source_db = source_db
        self.analytics_db = analytics_db
        self.server = None

    def run(self):
        try:
            if not getattr(sys, "frozen", False):
                backend_root = Path(__file__).resolve().parents[1] / "backend"
                if not backend_root.is_dir():
                    raise FileNotFoundError(f"Backend folder not found: {backend_root}")
                sys.path.insert(0, str(backend_root))
            # Frozen builds include app.main and scripts.* in the import table.
            data_dir = self.analytics_db.parent
            os.environ["SHERLOCK_SOURCE_DB"] = str(self.source_db)
            os.environ["SHERLOCK_ANALYTICS_DB"] = str(self.analytics_db)
            os.environ["SHERLOCK_ARCHIVE_RAW_DIR"] = str(data_dir / "binance_public_raw")
            os.environ["SHERLOCK_ARCHIVE_STAGING_DB"] = str(data_dir / "binance_archive_staging.db")
            import uvicorn
            from app.main import app as fastapi_app
            config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=8000, log_level="warning", access_log=False)
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def stop(self):
        if self.server is not None:
            self.server.should_exit = True
        self.wait(7000)
