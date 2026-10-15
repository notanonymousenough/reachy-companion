[CmdletBinding()]
param(
    [string]$InventoryPath = '',
    [string]$PythonExecutable = 'py',
    [ValidateRange(3,60)][int]$TimeoutSeconds = 15,
    [ValidateRange(5,300)][int]$TotalTimeoutSeconds = 90,
    [switch]$DryRun,
    [switch]$WhatIf,
    [switch]$PauseIfInteractive
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$stopCode = 2
try {
    $stopDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ReachyCompanion'
    $stopLatch = Join-Path $stopDirectory 'manual-stop.json'
    if (-not ($DryRun -or $WhatIf)) {
        [void][IO.Directory]::CreateDirectory($stopDirectory)
        if (-not (Test-Path -LiteralPath $stopLatch)) {
            try {
                $stopStream = [IO.File]::Open($stopLatch, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
                try {
                    $stopMarker = @{schema=1;kind='reachy_manual_stop';request_id=[Guid]::NewGuid().ToString();requested_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json -Compress
                    $stopBytes = [Text.Encoding]::UTF8.GetBytes($stopMarker)
                    $stopStream.Write($stopBytes,0,$stopBytes.Length)
                    $stopStream.Flush($true)
                } finally { $stopStream.Dispose() }
            } catch { if (-not (Test-Path -LiteralPath $stopLatch)) { throw } }
        }
    }
    if (-not $InventoryPath) { $InventoryPath = Join-Path $stopDirectory 'stop-inventory.local.json' }
    $stopArguments = @('-B', (Join-Path $PSScriptRoot 'stop_reachy.py'), '--inventory', $InventoryPath,
        '--latch-path', $stopLatch, '--timeout', [string]$TimeoutSeconds, '--total-timeout', [string]$TotalTimeoutSeconds)
    if ($DryRun -or $WhatIf) { $stopArguments += '--dry-run' }
    if ([IO.Path]::GetFileName($PythonExecutable) -in @('py','py.exe')) { $stopArguments = @('-3') + $stopArguments }
    & $PythonExecutable @stopArguments
    $stopCode = $LASTEXITCODE
} catch {
    Write-Host 'Reachy stop incomplete. Check the Python launcher and private inventory; no automatic resume.'
} finally {
    # The CMD launcher may be double-clicked; redirected/SSH/CI runs never pause.
    if ($PauseIfInteractive -and -not $env:SSH_CONNECTION -and -not $env:CI -and [Environment]::UserInteractive) {
        try {
            if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
                Write-Host 'Press Enter to close this stop summary.'
                [void][Console]::ReadLine()
            }
        } catch { }
    }
}
exit $stopCode
