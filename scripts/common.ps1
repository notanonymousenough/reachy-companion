Set-StrictMode -Version Latest
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
        # Optional speaker EQ can be added by a newer profile after git pull.
        if ($profile.PSObject.Properties['tts'] -and $profile.tts.PSObject.Properties['playback_eq'] -and -not $settings.tts.PSObject.Properties['playback_eq']) {
            $settings.tts | Add-Member -NotePropertyName playback_eq -NotePropertyValue $profile.tts.playback_eq
        }
        if ($profile.PSObject.Properties['conversation'] -and $profile.conversation.PSObject.Properties['expressions'] -and -not $settings.conversation.PSObject.Properties['expressions']) {
            $settings.conversation | Add-Member -NotePropertyName expressions -NotePropertyValue $profile.conversation.expressions
        }
        if ($profile.PSObject.Properties['conversation'] -and $profile.conversation.PSObject.Properties['barge_in'] -and -not $settings.conversation.PSObject.Properties['barge_in']) {
            $settings.conversation | Add-Member -NotePropertyName barge_in -NotePropertyValue $profile.conversation.barge_in
        }
        Merge-CompanionSettings $settings $profile
    }
    return $settings
}
