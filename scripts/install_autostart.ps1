# Registers a Windows scheduled task so the collector starts with Windows.
#
# Without this, the scheduler only runs while someone has a terminal open,
# and stops at the first reboot. This is the local equivalent of the
# `scheduler` service in docker-compose.yml.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Status
#   powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -Remove
#
# Runs as the current user, at logon. No administrator rights needed, and
# nothing is installed outside Task Scheduler - -Remove undoes it entirely.

param(
    [switch]$Remove,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

$TaskName = 'AuctionPortalScheduler'
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $root 'scripts\run_scheduler.ps1'


function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Output "  not installed"
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Output "  task      : $TaskName"
    Write-Output "  state     : $($task.State)"
    Write-Output "  last run  : $($info.LastRunTime)"
    Write-Output "  last result: $($info.LastTaskResult)  (0 = ok, 267009 = currently running)"
    Write-Output "  next run  : $($info.NextRunTime)"
    Write-Output ""
    Write-Output "  log: $(Join-Path $root 'logs\scheduler.log')"
}


if ($Status) {
    Write-Output ""
    Show-Status
    Write-Output ""
    return
}

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "`n  removed $TaskName`n"
    }
    else {
        Write-Output "`n  $TaskName was not installed`n"
    }
    return
}

if (-not (Test-Path $runner)) {
    throw "Runner script missing: $runner"
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

# Highest is deliberately not requested: the task needs no privileges the
# user does not already have.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Collects bank auction listings and keeps the portal data current.' `
    -Force | Out-Null

Write-Output ""
Write-Output "  installed $TaskName"
Write-Output ""
Show-Status
Write-Output "  It will start at your next logon. To start it now:"
Write-Output "    Start-ScheduledTask -TaskName $TaskName"
Write-Output ""
