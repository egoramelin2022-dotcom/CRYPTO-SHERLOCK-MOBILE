# CRYPTO SHERLOCK Desktop

Windows desktop research terminal built with PySide6. It connects to the local read-only FastAPI market-data backend at `http://127.0.0.1:8000`.

## Run from repository root

```powershell
py -3.12 -m venv .venv-desktop
.\\.venv-desktop\\Scripts\\python.exe -m pip install -r desktop\\requirements.txt
.\\.venv-desktop\\Scripts\\python.exe -m desktop
```

The backend must be running with `SHERLOCK_SOURCE_DB` and `SHERLOCK_ANALYTICS_DB` configured. The desktop and backend environments are separate.

## Connected workflows

- Live Binance Spot candles and 24-hour ticker; symbols BTCUSDT, ETHUSDT, BNBUSDT and SOLUSDT; 15m, 1h, 4h and 1d.
- Historical Pattern Intelligence with free search and preserved five-stage mode.
- Multi-Timeframe scanner for aligned 15m / 4h / closed 1d data.
- Ensemble evidence aggregation. STUMPY is an optional research dependency; the UI reports when it is unavailable. Consensus is exact-window agreement only, not a probability.
- Backtesting Lab currently evaluates historical analog forward outcomes with configured fees and slippage. It is not yet a strategy-level walk-forward optimizer.
- Persistent manual Paper Trading spot ledger. Orders use public spot prices with simulated costs; no leverage, shorting or live exchange execution.
- Historical Binance monthly archive downloader with SHA256 verification into a separate staging database. The source database is never overwritten.

## Safety and current limitations

- No exchange API credentials or live order endpoints are implemented.
- Research only uses closed local candles and a contiguous suffix; missing intervals are not interpolated.
- The Paper Trading account is virtual and persisted in the separate analytics database. Default virtual starting cash is configurable with `SHERLOCK_PAPER_INITIAL_CASH`.
- Archive download can consume substantial disk space and time. It requires explicit confirmation and writes only to staging.
- This build still requires Windows smoke testing on the target PC. The generated executable is a portable folder build, not yet a signed MSI installer.
