"""Command-line entry point for historical market analytics."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

# Make "python backend/scripts/run_market_pipeline.py" work from repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.market_data.pipeline import run_historical_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, help="Existing candles SQLite DB (read-only)")
    parser.add_argument("--analytics-db", required=True, help="Separate output SQLite DB")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--window", type=int, default=20)
    args = parser.parse_args()
    result = run_historical_pipeline(
        args.source_db, args.analytics_db,
        symbol=args.symbol, interval=args.interval, window=args.window,
    )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
