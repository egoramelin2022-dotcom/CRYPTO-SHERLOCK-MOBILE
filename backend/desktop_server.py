"""Bundled local API server entry point for the Windows desktop package."""
import os
import sys

# PyInstaller --windowed builds may expose None for stdio streams. Uvicorn's
# logging handlers still expect writable streams, so safely redirect them.
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
