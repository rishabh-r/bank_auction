# Starts the database, then the scheduler, and keeps them running.
#
# Registered as a Windows scheduled task by install_autostart.ps1 so the
# portal keeps collecting after a reboot without anyone logging in and
# typing commands.
#
# Run it by hand to see what the scheduled task will do:
#   powershell -ExecutionPolicy Bypass -File scripts\run_scheduler.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Virtual environment missing. Run: python -m venv .venv"
}

New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
$log = Join-Path $root 'logs\scheduler.log'

function Write-Log($message) {
    $line = "{0} | {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    Write-Output $line
    Add-Content -Path $log -Value $line
}

Write-Log 'starting database'
& $python (Join-Path $root 'scripts\setup_postgres.py') --start | Out-Null

# The scheduler connects on its first job, which may be minutes away, but
# failing early with a clear message beats failing quietly later.
& $python -m auction_portal db | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log 'database unreachable, aborting'
    exit 1
}

Write-Log 'starting scheduler'
& $python -u -m auction_portal schedule *>&1 | Tee-Object -FilePath $log -Append

Write-Log "scheduler exited with code $LASTEXITCODE"
exit $LASTEXITCODE
