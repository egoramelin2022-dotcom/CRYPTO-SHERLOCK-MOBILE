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
- Local backend health check without blocking the UI.
- Explicit status labels; no fabricated prices, candle counts, scan results or progress.
- Research-only and Paper Trading only; no live order execution.

The Market Data, Pattern Intelligence, Multi-Timeframe, Ensemble, Backtesting and Paper Trading pages are foundation screens. Their real workflows will be connected incrementally to the existing backend and research modules. The verified Binance archive downloader remains a separate backend command until background-task orchestration and progress reporting are implemented.
