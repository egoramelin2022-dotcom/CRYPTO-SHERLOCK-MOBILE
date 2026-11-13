# Binance Spot Historical Kline Ingestion

Script: `backend/scripts/download_binance_spot_klines.py`

Downloads monthly BTCUSDT Spot kline ZIP archives for 15m, 4h and 1d from Binance Public Data Vision. The default range is 2017-08 through 2026-11; it can be narrowed with `--start` and `--end`.

## Safety and integrity

- Raw ZIPs and checksum sidecars are cached under `data/binance_public_raw`.
- Every archive is SHA256-verified before parsing.
- A failed checksum deletes the suspect archive and stops the run.
- Binance Spot timestamps from 2025 onward are microseconds; the loader normalizes them to milliseconds.
- Each candle is validated against the canonical Candle model.
- Data is ingested into a separate `data/binance_archive_staging.db` database by default.
- Existing candle rows are never overwritten; inserts are idempotent.
- HTTP 404 monthly archives are logged as missing; other network or server errors stop the run.

## Run on Windows

From the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe -m scripts.download_binance_spot_klines --start 2017-08 --end 2026-11
```

If the virtual environment is at repository root, use the matching Python executable instead. The first full download is large and may take a while. Keep the PC connected to power and use a stable internet connection.

The script is a staging ingestion tool. Do not point it at the existing production/source database. After ingestion, audit row counts, time ranges, duplicates and gaps before changing any research data-source configuration.
