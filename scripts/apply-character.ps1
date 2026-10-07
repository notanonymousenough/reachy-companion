param([string]$Configuration = "config.local.json", [string]$Profile = "profiles/friend.json")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$characterRepo = Split-Path -Parent $PSScriptRoot
Set-Location $characterRepo
$characterPatch = Get-Content -Raw -Encoding UTF8 $Profile | ConvertFrom-Json
function Merge-CharacterSettings {
    param($Target, $Patch)
    foreach ($characterProperty in $Patch.PSObject.Properties) {
        $characterExisting = $Target.PSObject.Properties[$characterProperty.Name]
        if ($null -eq $characterExisting) { throw "Unknown configuration field: $($characterProperty.Name)" }
        if ($characterProperty.Value -is [System.Management.Automation.PSCustomObject]) {
            Merge-CharacterSettings -Target $characterExisting.Value -Patch $characterProperty.Value
        } else {
            $characterExisting.Value = $characterProperty.Value
        }
    }
}
$characterFiles = @($Configuration)
if (Test-Path "config.worker.local.json") { $characterFiles += "config.worker.local.json" }
$characterPlans = @()
foreach ($characterFile in ($characterFiles | Select-Object -Unique)) {
    $characterSettings = Get-Content -Raw -Encoding UTF8 $characterFile | ConvertFrom-Json
    if ($characterPatch.PSObject.Properties['tts'] -and $characterPatch.tts.PSObject.Properties['playback_eq'] -and -not $characterSettings.tts.PSObject.Properties['playback_eq']) {
        $characterSettings.tts | Add-Member -NotePropertyName playback_eq -NotePropertyValue $characterPatch.tts.playback_eq
    }
    if ($characterPatch.PSObject.Properties['conversation'] -and $characterPatch.conversation.PSObject.Properties['expressions'] -and -not $characterSettings.conversation.PSObject.Properties['expressions']) {
        $characterSettings.conversation | Add-Member -NotePropertyName expressions -NotePropertyValue $characterPatch.conversation.expressions
    }
    Merge-CharacterSettings -Target $characterSettings -Patch $characterPatch
    $characterPlans += [pscustomobject]@{ Path = $characterFile; Settings = $characterSettings }
}
foreach ($characterPlan in $characterPlans) {
    $characterBackup = $characterPlan.Path -replace '\.json$', '.before-character.local.json'
    if (-not (Test-Path $characterBackup)) { Copy-Item $characterPlan.Path $characterBackup }
    $characterTemporary = $characterPlan.Path + ".tmp"
    [System.IO.File]::WriteAllText((Join-Path $characterRepo $characterTemporary), ($characterPlan.Settings | ConvertTo-Json -Depth 32), [System.Text.UTF8Encoding]::new($false))
    Move-Item -Force $characterTemporary $characterPlan.Path
}
if (Test-Path "config.worker.local.json") {
    $characterWorker = Get-Content -Raw -Encoding UTF8 "config.worker.local.json" | ConvertFrom-Json
    & docker restart ([string]$characterWorker.container.name)
    if ($LASTEXITCODE -ne 0) { throw "Configuration saved, but worker restart failed. Start Docker and rerun this script." }
    $characterReady = $false
    foreach ($characterAttempt in 1..30) {
        try {
            $characterHealth = Invoke-RestMethod -Uri "http://localhost:$($characterWorker.servers.worker.port)/health" -TimeoutSec 2
            if ($characterHealth.ok) { $characterReady = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $characterReady) { throw "Worker did not become ready. Check docker logs." }
    Write-Host "New character applied. Worker ready."
} else {
    Write-Host "Profile saved. Run scripts/start-worker.ps1 to create the worker."
}
