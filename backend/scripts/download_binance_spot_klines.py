"""Download and ingest Binance Spot monthly kline archives with SHA256 checks.

Downloads are cached as immutable ZIP files. The SQLite target defaults to a
separate staging database and never overwrites an existing candle row.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import io
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterator, Callable

from app.market_data.candles import Candle
from app.market_data.repository import CandleRepository

BASE = "https://data.binance.vision/data/spot/monthly/klines"
INTERVALS = ("15m", "4h", "1d")
COLUMNS = 12


def months_between(start_year: int, start_month: int, end_year: int, end_month: int):
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        yield year, month
        if month == 12:
            year, month = year + 1, 1
        else:
            year, month = year, month + 1


def normalize_timestamp(value: str) -> int:
    """Normalize Binance Spot millisecond or microsecond epoch timestamps."""
    timestamp = int(value)
    if timestamp < 0:
        raise ValueError("timestamp must be nonnegative")
    if timestamp >= 100_000_000_000_000:
        timestamp //= 1_000
    elif timestamp < 100_000_000_000:
        raise ValueError(f"unsupported Binance timestamp precision: {value!r}")
    return timestamp


def normalize_kline_times(open_value: str, close_value: str, interval: str) -> tuple[int, int]:
    """Normalize timestamps and canonicalize an exact exclusive close boundary."""
    from app.market_data.intervals import interval_to_ms

    raw_open = int(open_value)
    raw_close = int(close_value)
    open_is_microseconds = raw_open >= 100_000_000_000_000
    close_is_microseconds = raw_close >= 100_000_000_000_000
    if open_is_microseconds != close_is_microseconds:
        raise ValueError("open_time and close_time use different timestamp precisions")
    if open_is_microseconds and (raw_open % 1_000 or raw_close % 1_000):
        raise ValueError("microsecond timestamps must represent exact millisecond boundaries")
    open_time = normalize_timestamp(open_value)
    close_time = normalize_timestamp(close_value)
    expected_close = open_time + interval_to_ms(interval) - 1
    # Internal storage uses the final millisecond (inclusive close).
    # Accept an archive that encodes the exact interval end as exclusive.
    if close_time == expected_close + 1:
        close_time = expected_close
    if close_time != expected_close:
        raise ValueError(
            f"{interval} close_time mismatch: open={open_time}, close={close_time}, "
            f"expected inclusive close={expected_close}, delta={close_time - open_time}ms"
        )
    return open_time, close_time


def parse_checksum(text: str) -> str:
    parts = text.strip().split()
    if not parts:
        raise ValueError("empty checksum response")
    digest = parts[0].lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid SHA256 checksum")
    return digest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: Path) -> bool:
    """Download URL atomically. Return False only for HTTP 404."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "CRYPTO-SHERLOCK/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except urllib.error.HTTPError as exc:
        temporary.unlink(missing_ok=True)
        if exc.code == 404:
            return False
        raise
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(destination)
    return True


def archive_url(symbol: str, interval: str, year: int, month: int) -> str:
    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    return f"{BASE}/{symbol}/{interval}/{filename}"


def iter_archive_candles(archive: Path, symbol: str, interval: str) -> Iterator[Candle]:
    with zipfile.ZipFile(archive) as zipped:
        csv_names = [name for name in zipped.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"expected one CSV in {archive.name}, found {len(csv_names)}")
        with zipped.open(csv_names[0]) as binary:
            text_stream = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            reader = csv.reader(text_stream)
            for line_number, row in enumerate(reader, start=1):
                if not row:
                    continue
                if len(row) != COLUMNS:
                    raise ValueError(f"{archive.name}:{line_number}: expected 12 columns, got {len(row)}")
                open_time, close_time = normalize_kline_times(row[0], row[6], interval)
                candle = Candle(
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    close_time=close_time,
                    quote_volume=float(row[7]),
                    trade_count=int(row[8]),
                    taker_buy_base=float(row[9]),
                    taker_buy_quote=float(row[10]),
                )
                try:
                    candle.validate()
                except ValueError as exc:
                    raise ValueError(
                        f"{archive.name}:{line_number}: invalid {interval} candle "
                        f"(open_time={open_time}, close_time={close_time}): {exc}"
                    ) from exc
                yield candle


def ingest_month(
    symbol: str, interval: str, year: int, month: int,
    raw_dir: Path, repository: CandleRepository,
) -> tuple[int, str]:
    url = archive_url(symbol, interval, year, month)
    filename = url.rsplit("/", 1)[1]
    archive = raw_dir / symbol / interval / filename
    checksum_path = Path(str(archive) + ".CHECKSUM")

    if not archive.exists():
        if not download_file(url, archive):
            return 0, "missing"
    checksum_url = url + ".CHECKSUM"
    if not checksum_path.exists():
        if not download_file(checksum_url, checksum_path):
            raise RuntimeError(f"checksum file is missing for {filename}")
    expected = parse_checksum(checksum_path.read_text(encoding="utf-8"))
    actual = sha256_file(archive)
    if actual != expected:
        archive.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        raise RuntimeError(f"SHA256 mismatch for {filename}; corrupt archive removed")

    inserted = 0
    batch: list[Candle] = []
    for candle in iter_archive_candles(archive, symbol, interval):
        batch.append(candle)
        if len(batch) >= 5000:
            inserted += repository.insert_many(batch)
            batch.clear()
    if batch:
        inserted += repository.insert_many(batch)
    return inserted, "ok"


def _parse_month(value: str, field_name: str) -> tuple[int, int]:
    if (
        not isinstance(value, str) or len(value) != 7
        or value[4] != "-" or not value[:4].isdigit()
        or not value[5:].isdigit()
    ):
        raise ValueError(f"{field_name} must use exact YYYY-MM format")
    year, month = int(value[:4]), int(value[5:])
    if year < 2017 or not 1 <= month <= 12:
        raise ValueError(f"{field_name} is outside supported Binance Spot archive range")
    return year, month


def run(start: str, end: str, raw_dir: Path, db_path: Path, progress_callback: Callable[[str], None] | None = None) -> int:
    start_year, start_month = _parse_month(start, "start month")
    end_year, end_month = _parse_month(end, "end month")
    if (start_year, start_month) > (end_year, end_month):
        raise ValueError("start month must not be after end month")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)
        else:
            print(message)
    try:
        repository = CandleRepository(connection)
        repository.ensure_schema()
        total_inserted = 0
        missing_archives: list[str] = []
        for interval in INTERVALS:
            for year, month in months_between(start_year, start_month, end_year, end_month):
                inserted, status = ingest_month(
                    "BTCUSDT", interval, year, month, raw_dir, repository
                )
                total_inserted += inserted
                if status == "missing":
                    missing_archives.append(f"{interval} {year}-{month:02d}")
                emit(f"{interval} {year}-{month:02d}: {status}; inserted={inserted}")
        for interval in INTERVALS:
            emit(f"TOTAL BTCUSDT {interval}: {repository.count('BTCUSDT', interval)} rows")
        emit(f"TOTAL inserted this run: {total_inserted}")
        if missing_archives:
            missing_text = ", ".join(missing_archives)
            raise RuntimeError(
                "Archive download is incomplete: Binance returned HTTP 404 for "
                f"requested monthly archives: {missing_text}. Data already ingested "
                "remains in staging; rerun after verifying archive availability."
            )
        return total_inserted
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    latest_complete_month = (
        datetime.now(timezone.utc).replace(day=1) - timedelta(days=1)
    ).strftime("%Y-%m")
    parser.add_argument("--start", default="2017-08", help="first YYYY-MM (default: 2017-08)")
    parser.add_argument("--end", default=latest_complete_month,
                        help=f"last YYYY-MM (default: {latest_complete_month})")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/binance_public_raw"))
    parser.add_argument("--db-path", type=Path, default=Path("data/binance_archive_staging.db"))
    args = parser.parse_args()
    try:
        run(args.start, args.end, args.raw_dir, args.db_path)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
