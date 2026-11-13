# Home Server Runbook

Complete each gate before proceeding.

## Gate 0 — protect existing work
- Do not reinstall Windows or delete/move the project.
- Back up C:\\CRYPTO_SHERLOCK\\data to a separate physical drive.
- Never share passwords, SSH keys, Tailscale auth keys or screenshots containing secrets.

## Gate 1 — local backend
- Confirm repository and database paths; verify source and analytics DB are separate.
- Confirm Python launcher/version.
- Run backend/start_server_windows.ps1 manually.
- Verify http://127.0.0.1:8000/health and a small live Binance kline request.
Pass only when both health and live candles succeed.

## Gate 2 — Windows reliability
- Disable sleep while plugged in; reserve the PC DHCP address in the router.
- Install the scheduled task after manual startup passes.
- Verify task starts after logon and configure analytics backup on a separate disk.
Pass only when backend starts and SQLite backup integrity check passes.

## Gate 3 — private remote access
- Install Tailscale on Windows and Android; approve both devices.
- Test http://PC-TAILSCALE-IP:8000/health over mobile data with Wi-Fi off.
- Do not add router port-forwarding rules.

## Gate 4 — Android integration
- Set app server URL to PC Tailscale IP and port 8000.
- Verify ticker/candles; only then run audit and research pipeline.

## Gate 5 — hardening
- Add persistent job state, structured logs, job cancellation and resource limits.
- Add application authentication before access beyond trusted tailnet.
- Add off-device backups and test restore.
- Public HTTPS exposure is not required for Tailscale mode.