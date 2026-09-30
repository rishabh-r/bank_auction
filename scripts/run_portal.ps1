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
#
# Note on error handling: $ErrorActionPreference is deliberately NOT set
# to 'Stop'. PowerShell can treat a native program merely writing to
# stderr as a terminating error, and pg_ctl does that routinely on
# startup. An earlier version of this script died silently at exactly
# that point, leaving the database up and nothing else running. Every
# step here is therefore checked explicitly and logged.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Path (Join-Path $root 'logs') -Force | Out-Null
$log = Join-Path $root 'logs\portal.log'

function Write-Log($message) {
    $line = "{0} | {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
    Write-Output $line
    try { Add-Content -Path $log -Value $line -ErrorAction SilentlyContinue } catch { }
}

Write-Log '--- starting ---'

if (-not (Test-Path $python)) {
    Write-Log "FATAL: no virtual environment at $python"
    exit 1
}

# --- 1. database ----------------------------------------------------------
# Give Postgres several attempts: at logon the disk is busy and a previous
# unclean shutdown may need recovering first.
$dbReady = $false
foreach ($attempt in 1..5) {
    Write-Log "starting database (attempt $attempt of 5)"
    & $python (Join-Path $root 'scripts\setup_postgres.py') --start 2>&1 |
        ForEach-Object { Write-Log "  pg: $_" }

    & $python -m auction_portal db 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $dbReady = $true
        Write-Log 'database ready'
        break
    }

    Write-Log 'database not ready yet, waiting 15s'
    Start-Sleep -Seconds 15
}

if (-not $dbReady) {
    Write-Log 'FATAL: database never became reachable, giving up'
    exit 1
}

# --- 2. web server --------------------------------------------------------
# Skip if something already holds the port, so a manually started portal
# is not clobbered.
$inUse = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Log 'port 8000 already serving, leaving it alone'
}
else {
    Write-Log 'starting web server on port 8000'
    try {
        Start-Process -FilePath $python `
            -ArgumentList '-u', '-m', 'auction_portal', 'serve' `
            -RedirectStandardOutput (Join-Path $root 'logs\web.log') `
            -RedirectStandardError (Join-Path $root 'logs\web.err') `
            -WindowStyle Hidden
    }
    catch {
        # The site failing is not a reason to skip collecting data.
        Write-Log "web server failed to start: $($_.Exception.Message)"
    }
}

# --- 3. bring data up to date --------------------------------------------
# After downtime, statuses are stale. Correct them before the scheduler's
# own timer would get round to it.
Write-Log 'running maintenance'
& $python -m auction_portal maintain 2>&1 | ForEach-Object { Write-Log "  $_" }

# --- 4. scheduler ---------------------------------------------------------
Write-Log 'starting scheduler (runs until stopped)'
& $python -u -m auction_portal schedule 2>&1 | ForEach-Object { Write-Log $_ }

Write-Log "scheduler exited with code $LASTEXITCODE"
exit $LASTEXITCODE
