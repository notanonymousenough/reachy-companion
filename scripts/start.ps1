param([string]$Configuration = 'config.local.json', [switch]$NoPull)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$companionRepo = Split-Path -Parent $PSScriptRoot
Set-Location $companionRepo
. "$PSScriptRoot/common.ps1"
$settings = Read-CompanionSettings $Configuration
if (-not $NoPull) {
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'This directory must be a Git checkout.' }
    if ($dirty) { throw 'Tracked files have local changes. Commit or stash them before updating.' }
    & git pull --ff-only ([string]$settings.runtime.git.remote) ([string]$settings.runtime.git.branch)
    if ($LASTEXITCODE -ne 0) { throw 'Git pull failed; existing services were not restarted.' }
    # Run the newly pulled script, including any changes to startup logic itself.
    & powershell -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot/start.ps1" -Configuration $Configuration -NoPull
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed after pull.' }
    exit 0
}
$deadline = (Get-Date).AddSeconds([int]$settings.runtime.windows.startup_timeout)
$initialDockerReady = $false
try {
    & docker info --format '{{.OSType}}' 2>$null | Out-Null
    $initialDockerReady = $LASTEXITCODE -eq 0
} catch { }
if (-not $initialDockerReady) {
    Start-Process -FilePath ([string]$settings.runtime.windows.docker_desktop_path)
}
$dockerReady = $false
while ((Get-Date) -lt $deadline) {
    try {
        $dockerOS = & docker info --format '{{.OSType}}' 2>$null
        if ($LASTEXITCODE -eq 0 -and "$dockerOS".Trim() -eq 'linux') { $dockerReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $dockerReady) { throw 'Docker Linux engine did not become ready.' }
$lms = [string]$settings.runtime.windows.lms_command
& $lms daemon up
if ($LASTEXITCODE -ne 0) { throw 'Cannot start LM Studio daemon.' }
$loadedJSON = & $lms ps --json
if ($LASTEXITCODE -ne 0) { throw 'Cannot query loaded models.' }
$loaded = $loadedJSON | ConvertFrom-Json
if (-not ($loaded | Where-Object { $_.identifier -eq $settings.llm.model })) {
    & $lms load ([string]$settings.runtime.windows.model_key) --identifier ([string]$settings.llm.model) --gpu ([string]$settings.runtime.windows.gpu) --context-length ([int]$settings.runtime.windows.context_length) --yes
    if ($LASTEXITCODE -ne 0) { throw 'Cannot load the configured LLM.' }
}
$llmURL = [uri]$settings.container.desktop_llm_base_url
& $lms server start --port $llmURL.Port --bind ([string]$settings.runtime.windows.llm_bind)
if ($LASTEXITCODE -ne 0) { throw 'Cannot start the LLM HTTP server.' }
# Validate an actual generation, not just /models (which can list unloaded models).
$probePrompt = $settings.llm.message_template.Replace('{role}','user').Replace('{content}','Say OK.') + $settings.llm.assistant_prefix
$probeBody = @{model=$settings.llm.model; prompt=$probePrompt; max_tokens=8; temperature=0; stream=$false; stop=$settings.llm.stop} | ConvertTo-Json -Depth 8
$probe = Invoke-RestMethod -Uri "http://127.0.0.1:$($llmURL.Port)/v1/completions" -Method Post -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($probeBody)) -TimeoutSec ([int]$settings.runtime.windows.startup_timeout)
if (-not $probe.choices) { throw 'LLM did not return a completion.' }
& "$PSScriptRoot/start-worker.ps1" -Configuration $Configuration
Write-Host 'Reachy stack ready: LLM + compute worker.'
