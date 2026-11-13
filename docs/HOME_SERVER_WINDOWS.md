# CRYPTO SHERLOCK Home Server — Windows 10

## Target

Use the existing Windows PC as the compute host; no VPS is required.
- Intel Core i5-2400, 16 GB RAM, Ethernet to router.
- 500 GB NVMe for project/data; 128 GB SSD for OS/temp; 500 GB HDD for backups.
- FastAPI/Uvicorn backend on port 8000; Tailscale for private remote access.
- Public Binance market data only. Research, backtesting and paper trading only; no real orders.

## Current backend paths

The backend startup script is backend/start_server_windows.ps1. By default it expects data/sherlock_market.db and writes derived results to data/sherlock_analytics.db. Set SHERLOCK_SOURCE_DB and SHERLOCK_ANALYTICS_DB to override. These paths must be different. Research opens the source database read-only.

## First-time setup

1. Back up the entire C:\\CRYPTO_SHERLOCK\\data folder to a separate physical disk before changes.
2. Confirm the source DB exists and locate the repository.
3. Prefer Python 3.12; run py --list to inspect installed versions.
4. In PowerShell, run backend\\start_server_windows.ps1 manually.
5. Verify http://127.0.0.1:8000/health and request three BTCUSDT 15m candles from /v1/market/klines.
6. Do not install auto-start until manual health and live market-data checks pass.

## Automatic start

After manual verification, run PowerShell as the Windows user who owns the data:

    Set-ExecutionPolicy -Scope Process Bypass
    .\\backend\\scripts\\install_home_server_task.ps1 -SourceDb 'C:\\CRYPTO_SHERLOCK\\data\\sherlock_market.db' -AnalyticsDb 'C:\\CRYPTO_SHERLOCK\\data\\sherlock_analytics.db'
    Start-ScheduledTask -TaskName 'CRYPTO-SHERLOCK-Backend'

The task starts at interactive logon and restarts on failure. It does not store a Windows password. The user must sign in after reboot.

## Power and network

- Use Ethernet. Reserve the PC DHCP address in the router after checking its actual address.
- Set Windows sleep to Never while plugged in; display may turn off.
- Do not port-forward 8000 on the router and do not expose Uvicorn to the public internet.
- Windows 10 standard support has ended; keep the system on a supported security-update path where available.

## Tailscale private access

1. Install Tailscale on Windows from https://tailscale.com/download/windows and install the Android app.
2. Sign in to the same tailnet and approve both devices.
3. Note the PC Tailscale IPv4 address.
4. Turn Wi-Fi off on the phone and test http://PC-TAILSCALE-IP:8000/health over mobile data.
5. Only after the health check succeeds, set that base URL in CRYPTO SHERLOCK Android settings.

Tailscale is the private network boundary. The current API has no app-level authentication; keep it restricted to trusted tailnet devices. Do not add more users or publish it publicly until authentication, TLS, rate limiting and redacted logs are implemented.

## Analytics backup

Run backend/scripts/backup_analytics_windows.ps1. It uses SQLite's online backup API, checks PRAGMA integrity_check and retains the newest 14 backups. Set BackupDir to the separate HDD, for example D:\\CRYPTO_SHERLOCK_BACKUPS\\analytics. Back up the source market database separately before any repair or migration.

## Known limitations

- Research job state is process-local and is lost on server restart.
- Current pipeline extracts features/regimes; it is not a validated trading strategy.
- Pattern Intelligence is early-stage. Five-stage mode compares five equal-length segments; it does not semantically detect the five named market phases.
- CI does not prove physical Android device operation.
- No exchange credentials or real order execution.

## Acceptance checklist

- [ ] Source DB backed up; paths confirmed.
- [ ] Backend starts manually; health endpoint returns status ok.
- [ ] Live Binance candles return.
- [ ] Scheduled task starts after logon.
- [ ] PC stays awake and online over Ethernet.
- [ ] Tailscale connects PC and Android.
- [ ] Health endpoint works over mobile data.
- [ ] Android loads live ticker/candles from home backend.
- [ ] Analytics backup passes SQLite integrity check.