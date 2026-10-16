Set-StrictMode -Version Latest
function Invoke-CompanionAcceptedRuntimeVerification {
    param([string]$Configuration, [string]$PythonExecutable = 'py')
    Assert-CompanionNotManuallyStopped
    $verifyRepo = Split-Path -Parent $PSScriptRoot
    $verifyConfiguration = if ([IO.Path]::IsPathRooted($Configuration)) { $Configuration } else { Join-Path $verifyRepo $Configuration }
    $verifyArguments = @('-I','-B',(Join-Path $PSScriptRoot 'windows/verify_startup.py'),'--configuration',$verifyConfiguration)
    if ([IO.Path]::GetFileName($PythonExecutable) -in @('py','py.exe')) { $verifyArguments = @('-3') + $verifyArguments }
    & $PythonExecutable @verifyArguments
    if ($LASTEXITCODE -ne 0) { throw 'Accepted-runtime verification denied; no bootstrap fallback is permitted.' }
    Assert-CompanionNotManuallyStopped
    Write-Host 'Pinned adapter returned read-only verification; runtime/slot integration requires its separate reviewed acceptance.'
}

function Assert-CompanionNotManuallyStopped {
    $manualStopFile = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ReachyCompanion/manual-stop.json'
    $manualStopAncestor = [IO.Path]::GetDirectoryName($manualStopFile)
    while ($manualStopAncestor) {
        try {
            $manualStopAttributes = [IO.File]::GetAttributes($manualStopAncestor)
            if ($manualStopAttributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Manual-stop ancestor is a reparse point; startup denied.' }
        } catch [IO.FileNotFoundException] { } catch [IO.DirectoryNotFoundException] { }
        $manualStopAncestor = [IO.Path]::GetDirectoryName($manualStopAncestor)
    }
    # Only confirmed not-found permits startup. Access/sharing/IO errors throw.
    try { [void][IO.File]::GetAttributes($manualStopFile) }
    catch [IO.FileNotFoundException] { return }
    catch [IO.DirectoryNotFoundException] { return }
    throw 'Reachy was manually stopped. Review outstanding stops, then explicitly remove the per-user manual-stop.json to resume.'
}
function Merge-CompanionSettings {
    param($Target, $Patch)
    foreach ($property in $Patch.PSObject.Properties) {
        $existing = $Target.PSObject.Properties[$property.Name]
        if ($null -eq $existing) { throw "Unknown setting: $($property.Name)" }
        if ($property.Value -is [System.Management.Automation.PSCustomObject]) {
            Merge-CompanionSettings $existing.Value $property.Value
        } else { $existing.Value = $property.Value }
    }
}
function Add-CompanionDefaults {
    param($Target, $Defaults)
    foreach ($property in $Defaults.PSObject.Properties) {
        $existing = $Target.PSObject.Properties[$property.Name]
        if ($null -eq $existing) { $Target | Add-Member -NotePropertyName $property.Name -NotePropertyValue $property.Value }
        elseif ($property.Value -is [System.Management.Automation.PSCustomObject] -and $existing.Value -is [System.Management.Automation.PSCustomObject]) { Add-CompanionDefaults $existing.Value $property.Value }
    }
}
function Read-CompanionSettings {
    param([string]$Path)
    $settings = Get-Content -Raw -Encoding UTF8 $Path | ConvertFrom-Json
    if (-not $settings.PSObject.Properties['runtime']) {
        throw 'Add the runtime section from config.example.json to your local configuration.'
    }
    if ($settings.runtime.profile) {
        $profilePath = Join-Path (Split-Path -Parent (Resolve-Path $Path)) $settings.runtime.profile
        $profile = Get-Content -Raw -Encoding UTF8 $profilePath | ConvertFrom-Json
        foreach ($property in $profile.PSObject.Properties) {
            if ($property.Name -notin @('llm','tts','conversation')) { throw 'Profile may only change llm, tts and conversation.' }
        }
        $defaults = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot '../config.example.json') | ConvertFrom-Json
        Add-CompanionDefaults $settings $defaults
        Merge-CompanionSettings $settings $profile
    }
    return $settings
}
