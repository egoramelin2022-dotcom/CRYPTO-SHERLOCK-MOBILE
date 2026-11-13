"""Bundled local API server entry point for the Windows desktop package."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    log_path = Path(os.getenv(
        "SHERLOCK_SERVER_LOG",
        str(Path.home() / "AppData" / "Local" / "CRYPTO_SHERLOCK" / "server.log"),
    )).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream
    logging.basicConfig(
        level=logging.INFO,
        stream=stream,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
