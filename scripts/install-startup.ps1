param([string]$Configuration = 'config.local.json')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$startupRepo = Split-Path -Parent $PSScriptRoot
Set-Location $startupRepo
. "$PSScriptRoot/common.ps1"
$startupSettings = Read-CompanionSettings $Configuration
$startupUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$startupArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + "$PSScriptRoot/start.ps1" + '" -Configuration "' + $Configuration + '" -NoPull -InTask'
$startupAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $startupArguments -WorkingDirectory $startupRepo
$startupTrigger = New-ScheduledTaskTrigger -AtLogOn -User $startupUser
$startupPrincipal = New-ScheduledTaskPrincipal -UserId $startupUser -LogonType Interactive -RunLevel Limited
$startupOptions = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName ([string]$startupSettings.runtime.windows.startup_task) -Action $startupAction -Trigger $startupTrigger -Principal $startupPrincipal -Settings $startupOptions -Force | Out-Null
Write-Host 'Reachy stack starts on Windows user login. Updates are pulled only when you run start.ps1 without -NoPull.'
