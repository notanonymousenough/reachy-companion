param([string]$Configuration = 'config.local.json', [string]$PythonExecutable = 'py')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$startupRepo = Split-Path -Parent $PSScriptRoot
Set-Location $startupRepo
. "$PSScriptRoot/common.ps1"
Assert-CompanionNotManuallyStopped
$startupSettings = Read-CompanionSettings $Configuration
$startupUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$startupArguments = '-NoProfile -ExecutionPolicy Bypass -File "' + "$PSScriptRoot/start.ps1" + '" -Configuration "' + $Configuration + '" -NoPull -InTask -PythonExecutable "' + $PythonExecutable + '"'
$startupAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $startupArguments -WorkingDirectory $startupRepo
$startupTrigger = New-ScheduledTaskTrigger -AtLogOn -User $startupUser
$startupPrincipal = New-ScheduledTaskPrincipal -UserId $startupUser -LogonType Interactive -RunLevel Limited
$startupOptions = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
Assert-CompanionNotManuallyStopped
Register-ScheduledTask -TaskName ([string]$startupSettings.runtime.windows.startup_task) -Action $startupAction -Trigger $startupTrigger -Principal $startupPrincipal -Settings $startupOptions -Force | Out-Null
Write-Host 'Logon task delegates read-only accepted-runtime verification. Reviewed adapter integration is required; ordinary START never pulls or bootstraps.'
