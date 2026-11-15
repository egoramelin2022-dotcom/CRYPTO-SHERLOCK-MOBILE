$ErrorActionPreference = "Stop"

$backendDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $backendDir
$workspaceRoot = Split-Path -Parent $repoRoot

$sourceDb = Join-Path $workspaceRoot "data\sherlock_market.db"
$analyticsDb = Join-Path $workspaceRoot "data\sherlock_analytics.db"

if ($env:SHERLOCK_SOURCE_DB) { $sourceDb = $env:SHERLOCK_SOURCE_DB }
if ($env:SHERLOCK_ANALYTICS_DB) { $analyticsDb = $env:SHERLOCK_ANALYTICS_DB }

if (-not (Test-Path $sourceDb -PathType Leaf)) {
    throw "Source SQLite database not found: $sourceDb. Set SHERLOCK_SOURCE_DB to its full path."
}

$env:SHERLOCK_SOURCE_DB = (Resolve-Path $sourceDb).Path
$env:SHERLOCK_ANALYTICS_DB = $analyticsDb

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPath = Join-Path $backendDir ".venv"
    Write-Host "Creating backend virtual environment..."
    $created = $false

    # Prefer the CI-tested Python 3.12, but do not fail when the PC only has
    # another installed Python (for example, the user's existing 3.14 setup).
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $venvPath
        $created = ($LASTEXITCODE -eq 0)
    }
    if (-not $created) {
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            throw "Python launcher and python command were not found. Install Python 3.12+ and retry."
        }
        & python -m venv $venvPath
        $created = ($LASTEXITCODE -eq 0)
    }
    if (-not $created -or -not (Test-Path $venvPython)) {
        throw "Could not create backend virtual environment. Install Python 3.12+ and retry."
    }
}

Write-Host "Installing/checking backend dependencies..."
& $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host ""
Write-Host "CRYPTO SHERLOCK SERVER"
Write-Host "Source DB (read-only): $env:SHERLOCK_SOURCE_DB"
Write-Host "Analytics DB:          $env:SHERLOCK_ANALYTICS_DB"
Write-Host "API docs:              http://127.0.0.1:8000/docs"
Write-Host "Phone connection:      http://<THIS-PC-WIFI-IP>:8000"
Write-Host "Keep Windows Firewall access limited to Private networks."
Write-Host ""

Set-Location $backendDir
& $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000
