"""Read-only audit and manifest generation for existing Sherlock market data.

The source SQLite database is opened with SQLite mode=ro. This module never
creates tables, repairs rows, fills gaps, or writes into the source database.
Research output is returned as JSON-compatible data and may be saved by the
caller to a separate path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from typing import Any

from app.market_data.candles import find_gaps\nfrom app.market_data.intervals import interval_to_ms

_REQUIRED_COLUMNS = {
    "symbol", "interval", "open_time", "open", "high", "low", "close",
    "volume", "close_time", "quote_volume", "trade_count",
    "taker_buy_base", "taker_buy_quote",
}


def _readonly_connection(db_path: Path) -> sqlite3.Connection:
    absolute = db_path.expanduser().resolve()
    # URI mode=ro makes accidental writes fail at the SQLite layer.
    uri = f"file:{quote(absolute.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_sqlite_dataset(
    db_path: str | Path,
    *,
    table: str = "candles",
    include_sha256: bool = False,
) -> dict[str, Any]:
    """Audit a candle SQLite database without modifying it.

    Returns a manifest plus per-(symbol, interval) quality summaries. A full
    file checksum is optional because hashing a large DB is an extra full read.
    """
    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if not table.replace("_", "").isalnum():
        raise ValueError("table must be a simple SQLite identifier")

    stat = path.stat()
    with _readonly_connection(path) as connection:
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        table_row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if table_row is None:
            raise ValueError(f"required table not found: {table}")
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        missing = sorted(_REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"table {table} is missing required columns: {missing}")

        pairs = connection.execute(
            f'SELECT DISTINCT symbol, interval FROM "{table}" ORDER BY symbol, interval'
        ).fetchall()
        datasets: list[dict[str, Any]] = []
        for pair in pairs:
            symbol, interval = str(pair[0]), str(pair[1])
            rows = connection.execute(
                f'''SELECT open_time, open, high, low, close, volume, close_time,
                           quote_volume, trade_count, taker_buy_base, taker_buy_quote
                    FROM "{table}" WHERE symbol=? AND interval=? ORDER BY open_time''',
                (symbol, interval),
            ).fetchall()
            times = [int(row["open_time"]) for row in rows]
            gaps = find_gaps(times, interval) if times else []
            malformed = 0
            for row in rows:
                o, h, low, c = (row[k] for k in ("open", "high", "low", "close"))
                numeric = [row[k] for k in (
                    "open", "high", "low", "close", "volume", "quote_volume",
                    "taker_buy_base", "taker_buy_quote",
                )]
                try:
                    valid = all(v is not None and float(v) == float(v) and abs(float(v)) != float("inf") for v in numeric)
                    valid = valid and min(float(o), float(h), float(low), float(c)) > 0
                    valid = valid and float(h) >= max(float(o), float(c), float(low))
                    valid = valid and float(low) <= min(float(o), float(c), float(h))
                    valid = valid and all(float(row[k]) >= 0 for k in (
                        "volume", "quote_volume", "taker_buy_base", "taker_buy_quote"
                    ))
                    valid = valid and int(row["trade_count"]) >= 0
                    step_ms = interval_to_ms(interval)\n                    valid = valid and int(row["open_time"]) % step_ms == 0\n                    valid = valid and int(row["close_time"]) == int(row["open_time"]) + step_ms - 1
                except (TypeError, ValueError, OverflowError):
                    valid = False
                if not valid:
                    malformed += 1

            datasets.append({
                "symbol": symbol,
                "interval": interval,
                "rows": len(rows),
                "first_open_time_ms": times[0] if times else None,
                "last_open_time_ms": times[-1] if times else None,
                "duplicate_open_times": len(times) - len(set(times)),
                "missing_candles": sum(g.missing_candles for g in gaps),
                "gap_count": len(gaps),
                "malformed_rows": malformed,
                "gaps": [
                    {"previous_open_time_ms": g.previous_open_time,
                     "next_open_time_ms": g.next_open_time,
                     "missing_candles": g.missing_candles}
                    for g in gaps
                ],
            })

    manifest = {
        "manifest_version": "0.1.0",
        "dataset_id": hashlib.sha256(
            f"{path}|{stat.st_size}|{stat.st_mtime_ns}|{table}".encode("utf-8")
        ).hexdigest()[:24],
        "source": {"type": "sqlite", "path": str(path), "table": table,
                   "read_only": True},
        "file_size_bytes": stat.st_size,
        "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "sha256": _sha256_file(path) if include_sha256 else None,
        "integrity_check": integrity_rows,
        "datasets": datasets,
        "audit_created_utc": datetime.now(timezone.utc).isoformat(),
        "limitations": [
            "This is a structural and candle-quality audit, not a trading signal.",
            "The source database was opened read-only; no repair or gap filling was attempted.",
            "A null sha256 means full-file hashing was not requested.",
        ],
    }
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CRYPTO SHERLOCK SQLite data audit")
    parser.add_argument("database", help="Path to the existing SQLite database")
    parser.add_argument("--table", default="candles")
    parser.add_argument("--sha256", action="store_true", help="Hash the complete source DB")
    parser.add_argument("--output", help="Optional JSON report path (must be separate from source DB)")
    args = parser.parse_args()
    report = audit_sqlite_dataset(args.database, table=args.table, include_sha256=args.sha256)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        if output == Path(args.database).expanduser().resolve():
            raise ValueError("report output must not overwrite the source database")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
