<#
.SYNOPSIS
  Register a Windows Task Scheduler job that runs scheduler.py every N minutes (F5).
  Dang ky Task Scheduler chay scheduler.py dinh ky; tac vu chi dang khi den gio hen.

.DESCRIPTION
  - Runs as the current Windows user, only while that user is logged on
    (Chrome is visible: headless=False).
  - WakeToRun: wakes the PC from sleep. StartWhenAvailable: runs late if a start was missed.
  - MultipleInstances IgnoreNew + lock.py: never two runs at the same time.
  - Tasks later than LATE_GRACE_MINUTES (config.py) are marked "missed", not posted.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Plan plans\thang11.json
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Plan plans\thang11.json -DryRun
  powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1 -Remove
#>
param(
    [string]$Plan,
    [int]$EveryMinutes = 15,
    [string]$TaskName = "ShopeeVideoPoster",
    [switch]$DryRun,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

if (-not $Plan) { throw "Missing -Plan (vi du: -Plan plans\thang11.json)" }
if ($EveryMinutes -lt 1) { throw "-EveryMinutes must be >= 1" }

if (-not [System.IO.Path]::IsPathRooted($Plan)) { $Plan = Join-Path $ProjectDir $Plan }
$PlanPath = (Resolve-Path $Plan).Path
$Python = (Get-Command python).Source

# Validate the plan first: do not schedule a broken plan
& $Python (Join-Path $ProjectDir "scheduler.py") --plan $PlanPath --validate
if ($LASTEXITCODE -ne 0) { throw "Plan is invalid - see logs\app.log. Nothing was scheduled." }

$Arguments = "`"$(Join-Path $ProjectDir 'scheduler.py')`" --plan `"$PlanPath`""
if ($DryRun) { $Arguments += " --dry-run" }

$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Shopee video poster: python scheduler.py --plan $PlanPath" -Force | Out-Null

Write-Host "Registered '$TaskName': every $EveryMinutes minute(s), plan $PlanPath$(if ($DryRun) { ' (dry-run)' })."
Write-Host "Logs: $(Join-Path $ProjectDir 'logs\app.log')   Remove: -Remove"
