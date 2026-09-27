# Starts everything the portal needs, in order, and keeps it running.
#
#   1. the database
#   2. the web server      (background - serves the site)
#   3. the scheduler       (foreground - collects and maintains data)
#
# The scheduler runs in the foreground deliberately: the scheduled task
# stays alive as long as this script does, so Windows restarts the whole
# set if it dies.
#
# Registered as a scheduled task by install_autostart.ps1. Run it by hand
# to see exactly what that task will do:
#   powershell -ExecutionPolicy Bypass -File scripts\run_portal.ps1

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw "Virtual environment missing. Run: python -m venv .venv"
}

New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
$log = Join-Path $root 'logs\portal.log'
$webLog = Join-Path $root 'logs\web.log'

function Write-Log($message) {
    $line = "{0} | {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    Write-Output $line
    Add-Content -Path $log -Value $line
}

Write-Log 'starting database'
& $python (Join-Path $root 'scripts\setup_postgres.py') --start | Out-Null

# Fail loudly now rather than leaving a scheduler running against nothing.
& $python -m auction_portal db | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log 'database unreachable, aborting'
    exit 1
}

# Only start the web server if nothing already holds the port, otherwise
# a manually started portal would be killed by a silent bind failure.
$inUse = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Log 'port 8000 already serving, leaving it alone'
}
else {
    Write-Log 'starting web server on port 8000'
    Start-Process -FilePath $python `
        -ArgumentList '-u', '-m', 'auction_portal', 'serve' `
        -RedirectStandardOutput $webLog `
        -RedirectStandardError (Join-Path $root 'logs\web.err') `
        -WindowStyle Hidden
}

Write-Log 'starting scheduler'
& $python -u -m auction_portal schedule *>&1 | Tee-Object -FilePath $log -Append

Write-Log "scheduler exited with code $LASTEXITCODE"
exit $LASTEXITCODE
