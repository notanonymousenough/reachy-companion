param([string]$Configuration = 'config.local.json')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$controlRoot = Split-Path -Parent $PSScriptRoot
Set-Location $controlRoot
. (Join-Path $PSScriptRoot 'common.ps1')
$settings = Read-CompanionSettings $Configuration
$controlTokenPath = Join-Path $controlRoot $settings.paths.token_file
$controlToken = (Get-Content -Raw $controlTokenPath).Trim()
Start-Process ($settings.network.hub_url + '/control#' + [uri]::EscapeDataString($controlToken))
Write-Host ('Control page opened: ' + $settings.network.hub_url + '/control')
