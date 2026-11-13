"""Bundled local API server entry point for the Windows desktop package."""
import os
import sys
from pathlib import Path

# PyInstaller --windowed builds may expose None for stdio streams. Uvicorn's
# logging handlers still expect writable streams, so safely redirect them.
log_path = os.getenv("SHERLOCK_SERVER_LOG")
if log_path:
    Path(log_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    log_stream = open(Path(log_path).expanduser(), "a", encoding="utf-8", buffering=1)
    sys.stdout = log_stream
    sys.stderr = log_stream
else:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
    )
