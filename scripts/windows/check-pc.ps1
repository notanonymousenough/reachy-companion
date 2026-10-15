param([string]$Configuration='config.local.json',[string]$PythonExecutable='py',[switch]$ConfigurationOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$checkRepo=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$checkPythonArgs=@('-B',(Join-Path $PSScriptRoot 'check_pc.py'),'--config',(Join-Path $checkRepo $Configuration))
if ([IO.Path]::GetFileName($PythonExecutable) -in @('py','py.exe')) { $checkPythonArgs=@('-3')+$checkPythonArgs }
& $PythonExecutable @checkPythonArgs
if ($LASTEXITCODE -ne 0) { throw 'PC configuration preflight failed; no services were changed.' }
Get-Command git,docker -ErrorAction Stop | Select-Object Name,Source
. (Join-Path $checkRepo 'scripts/common.ps1')
$checkSettings=Read-CompanionSettings (Join-Path $checkRepo $Configuration)
Get-Command ([string]$checkSettings.runtime.windows.lms_command) -ErrorAction Stop | Select-Object Name,Source
if (-not $ConfigurationOnly) {
    $checkDockerOS = & docker info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0 -or "$checkDockerOS".Trim() -ne 'linux') { throw 'Start Docker Desktop Linux engine before startup.' }
}
Write-Host 'Read-only PC configuration check passed. Verify LM Studio model key and LAN health using the clean-PC guide.'
