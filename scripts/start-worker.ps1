param([string]$Configuration = 'config.local.json', [string]$PythonExecutable = 'py')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/common.ps1"
Assert-CompanionNotManuallyStopped
Invoke-CompanionAcceptedRuntimeVerification -Configuration $Configuration -PythonExecutable $PythonExecutable
