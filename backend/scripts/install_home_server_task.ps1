param([string]$TaskName = "CRYPTO-SHERLOCK-Backend", [string]$SourceDb = "", [string]$AnalyticsDb = "")
$ErrorActionPreference = "Stop"
$backendDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startupScript = Join-Path $backendDir "start_server_windows.ps1"
if (-not (Test-Path $startupScript -PathType Leaf)) { throw "Backend startup script not found: $startupScript" }
if ($SourceDb) { [Environment]::SetEnvironmentVariable("SHERLOCK_SOURCE_DB", $SourceDb, "User") }
if ($AnalyticsDb) { [Environment]::SetEnvironmentVariable("SHERLOCK_ANALYTICS_DB", $AnalyticsDb, "User") }
$powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$startupScript`""
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments -WorkingDirectory $backendDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Starts the local CRYPTO SHERLOCK backend after user logon." -Force | Out-Null
Write-Host "Installed task: $TaskName"
Write-Host "Starts at interactive logon; PC must remain awake and connected."
Write-Host "Start now: Start-ScheduledTask -TaskName `"$TaskName`""