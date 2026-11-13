# CRYPTO SHERLOCK Desktop

Windows desktop research terminal built with PySide6. The portable Windows package includes a local FastAPI backend executable. The backend binds to `127.0.0.1:8000` only and is launched/stopped by the desktop application.

## Run from repository root

```powershell
py -3.12 -m venv .venv-desktop
.\\.venv-desktop\\Scripts\\python.exe -m pip install -r desktop\\requirements.txt
.\\.venv-desktop\\Scripts\\python.exe -m desktop
```

The Windows installer and portable folder include a local backend executable. Run `CRYPTO-SHERLOCK-Setup-0.3.0.exe`, then open **Server Settings**, select the existing `sherlock_market.db`, choose a separate analytics database path, then save and start the local server. The desktop launches the backend on `127.0.0.1:8000` and stops the process when the app closes. The source database is never used for writes.

## Connected workflows

The archive loader runs asynchronously and writes only to the staging database. The application polls job status instead of freezing the UI.

- Live Binance Spot candles and 24-hour ticker; symbols BTCUSDT, ETHUSDT, BNBUSDT and SOLUSDT; 15m, 1h, 4h and 1d.
- Historical Pattern Intelligence with free search and preserved five-stage mode. Five-stage matching reports five named positional stage scores with exactly 20% weight each. The top historical analogs are visualized against the current query. By default it loads up to 400,000 verified candles per market/timeframe. The latest query must be continuous; historical candidate windows and their forward-outcome paths that cross missing candles are skipped rather than silently bridged. Research reads the immutable source database plus verified archive staging data as a read-only merged view; conflicting duplicate candles are rejected. Gap counts and continuous segment counts are reported.
- Multi-Timeframe scanner for aligned 15m / 4h / closed 1d data. Each timeframe is split at missing-candle boundaries and only overlapping continuous segments are evaluated.
- Ensemble evidence aggregation. STUMPY is an optional research dependency; the UI reports when it is unavailable. Consensus is exact-window agreement only, not a probability.
- Backtesting Lab currently evaluates historical analog forward outcomes with configured fees and slippage. It is not yet a strategy-level walk-forward optimizer.
- Server Settings dialog with source/analytics path validation and bundled local backend lifecycle.\n- Persistent manual Paper Trading spot ledger. Orders use public spot prices with simulated costs; no leverage, shorting or live exchange execution.
- Historical Binance monthly archive downloader with SHA256 verification into a separate staging database. The source database is never overwritten.

## Safety and current limitations

- No exchange API credentials or live order endpoints are implemented. The local backend binds to loopback only; do not expose port 8000 publicly.
- Research only uses closed local candles. Missing intervals are never interpolated or crossed by candidate patterns, forward outcomes, STUMPY windows, or multi-timeframe scans. Verified history on both sides of gaps remains available where a complete contiguous window exists. Archive staging candles become available to research automatically after verification, without modifying the source database.
- The Paper Trading account is virtual and persisted in the separate analytics database. Default virtual starting cash is configurable with `SHERLOCK_PAPER_INITIAL_CASH`.
- Archive download can consume substantial disk space and time. It requires explicit confirmation and writes only to staging.
- This build still requires Windows smoke testing on the target PC. The generated installer is an unsigned per-user Inno Setup package; Windows SmartScreen may show the usual warning for an unsigned build.
