param([string]$AnalyticsDb = "", [string]$BackupDir = "")
$ErrorActionPreference = "Stop"
$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = Split-Path -Parent $backendDir
$workspaceRoot = Split-Path -Parent $repoRoot
if (-not $AnalyticsDb) { $AnalyticsDb = $env:SHERLOCK_ANALYTICS_DB }
if (-not $AnalyticsDb) { $AnalyticsDb = Join-Path $workspaceRoot "data\sherlock_analytics.db" }
if (-not $BackupDir) { $BackupDir = Join-Path $workspaceRoot "backups\analytics" }
if (-not (Test-Path $AnalyticsDb -PathType Leaf)) { Write-Host "Analytics DB does not exist yet; nothing to back up."; exit 0 }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Backend venv Python not found: $python" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$destination = Join-Path $BackupDir "sherlock_analytics_$stamp.db"
$backupCode = @'
import sqlite3, sys
source, destination = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)
dst = sqlite3.connect(destination, timeout=30)
try:
    src.backup(dst)
    result = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok": raise RuntimeError(f"Backup integrity check failed: {result}")
finally:
    dst.close(); src.close()
print(destination)
@
& $python -c $backupCode $AnalyticsDb $destination
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed." }
Get-ChildItem -Path $BackupDir -Filter "sherlock_analytics_*.db" -File | Sort-Object LastWriteTime -Descending | Select-Object -Skip 14 | Remove-Item -Force
Write-Host "Verified analytics backup: $destination"