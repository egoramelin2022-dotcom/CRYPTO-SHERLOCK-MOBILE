# CRYPTO SHERLOCK Desktop

Windows desktop research terminal built with PySide6. The portable Windows package includes a local FastAPI backend executable. The backend binds to `127.0.0.1:8000` only and is launched/stopped by the desktop application.

## Run from repository root

```powershell
py -3.12 -m venv .venv-desktop
.\\.venv-desktop\\Scripts\\python.exe -m pip install -r desktop\\requirements.txt
.\\.venv-desktop\\Scripts\\python.exe -m desktop
```

The Windows package includes a local backend executable. Open **Server Settings**, select the existing `sherlock_market.db`, choose a separate analytics database path, then save and start the local server. Saving changed paths restarts the bundled backend. After a historical archive download completes, you can select the staging database as the source for a separate research run. The desktop launches the backend on `127.0.0.1:8000` and stops the process when the app closes. The source database is never used for writes.

## Connected workflows

The packaged desktop launches its local API service on loopback only after database paths are configured.

The archive loader runs asynchronously and writes only to the staging database. The application polls job status instead of freezing the UI.

- Live Binance Spot candles and 24-hour ticker; symbols BTCUSDT, ETHUSDT, BNBUSDT and SOLUSDT; 15m, 1h, 4h and 1d.
- Historical Pattern Intelligence with free search and preserved five-stage mode.
- Multi-Timeframe scanner for aligned 15m / 4h / closed 1d data.
- Ensemble evidence aggregation. STUMPY is an optional research dependency; the UI reports when it is unavailable. Consensus is exact-window agreement only, not a probability.
- Backtesting Lab currently evaluates historical analog forward outcomes with configured fees and slippage. It is not yet a strategy-level walk-forward optimizer.
- Server Settings dialog with source/analytics path validation and bundled local backend lifecycle.\n- Persistent manual Paper Trading spot ledger. Orders use public spot prices with simulated costs; no leverage, shorting or live exchange execution.
- Historical Binance monthly archive downloader with SHA256 verification into a separate staging database. The source database is never overwritten.

## Safety and current limitations

- No exchange API credentials or live order endpoints are implemented. The local backend binds to loopback only; do not expose port 8000 publicly.
- Research only uses closed local candles and a contiguous suffix; missing intervals are not interpolated.
- The Paper Trading account is virtual and persisted in the separate analytics database. Default virtual starting cash is configurable with `SHERLOCK_PAPER_INITIAL_CASH`.
- Archive download can consume substantial disk space and time. It requires explicit confirmation and writes only to staging.
- This build still requires Windows smoke testing on the target PC. The generated application is a portable folder build, not yet a signed MSI installer.
