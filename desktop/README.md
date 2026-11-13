# CRYPTO SHERLOCK Desktop

Windows desktop research terminal built with PySide6. It connects to the existing read-only FastAPI backend at `http://127.0.0.1:8000`.

## Run from repository root (PowerShell, first-time setup)

```powershell
py -3.12 -m venv .venv-desktop
.\.venv-desktop\Scripts\python.exe -m pip install -r desktop\requirements.txt
.\.venv-desktop\Scripts\python.exe -m desktop
```

If Python 3.12 is not installed, install it before setup. The desktop environment is separate from the backend virtual environment to avoid dependency conflicts.

## Current scope

- Dark professional desktop shell and navigation.
- Local backend health check without blocking the UI.\n- Live Binance Spot ticker and OHLC candlestick chart for BTCUSDT, ETHUSDT, BNBUSDT and SOLUSDT, with 15m / 1h / 4h / 1d intervals.\n- Candle payload validation (finite values, OHLC bounds, timestamp ordering) before rendering.\n- Market requests run in a worker thread; API failures are displayed instead of fabricating data.
- Explicit status labels; no fabricated prices, candle counts, scan results or progress.
- Research-only and Paper Trading only; no live order execution.

Pattern Intelligence, Multi-Timeframe, Ensemble, Backtesting and Paper Trading pages remain integration screens; they do not yet expose complete interactive workflows. The verified Binance archive downloader remains a separate backend command until its progress and cancellation handling are safely integrated. This build is not yet a signed installer and requires a local Windows smoke test.
