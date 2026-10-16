param([string]$Configuration = 'config.local.json', [switch]$NoPull, [switch]$InTask, [int]$ContextLength = 0, [string]$PythonExecutable = 'py')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/common.ps1"
Assert-CompanionNotManuallyStopped
if ($ContextLength -ne 0) { throw 'Ordinary START cannot change accepted runtime context; explicit owned migration is required.' }
# NoPull/InTask remain argument-compatible; ordinary START never pulls or schedules.
Invoke-CompanionAcceptedRuntimeVerification -Configuration $Configuration -PythonExecutable $PythonExecutable
