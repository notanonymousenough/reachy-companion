param([string]$Configuration = "config.local.json", [string]$PythonExecutable = 'py')
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$workerRepo = Split-Path -Parent $PSScriptRoot
Set-Location $workerRepo
. "$PSScriptRoot/common.ps1"
Assert-CompanionNotManuallyStopped
& "$PSScriptRoot/windows/check-pc.ps1" -Configuration $Configuration -PythonExecutable $PythonExecutable -ConfigurationOnly
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required. Start it with Linux containers."
}
$workerDockerExe = [string](Get-Command docker -CommandType Application -ErrorAction Stop).Source
function Invoke-WorkerDocker {
    param([string[]]$DockerArguments)
    Assert-CompanionNotManuallyStopped
    $previousDockerConfig = $env:DOCKER_CONFIG
    try {
        $env:DOCKER_CONFIG = $workerClientDirectory
        & $workerDockerExe @workerDockerPrefix @DockerArguments
        if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($DockerArguments[0])" }
    } finally { $env:DOCKER_CONFIG = $previousDockerConfig }
}
$workerDockerOS = & $workerDockerExe info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $workerDockerOS.Trim() -ne "linux") {
    throw "Start Docker Desktop with Linux containers before running this script."
}
$workerConfigSource = Join-Path $workerRepo $Configuration
$workerSettings = Read-CompanionSettings $workerConfigSource
$workerTokenFile = Join-Path $workerRepo $workerSettings.paths.token_file
if (-not (Test-Path $workerTokenFile)) { throw "Copy the existing secrets/token from your Mac repository." }
if ((Get-Content -Raw $workerTokenFile).Trim().Length -lt 32) { throw "Invalid companion token." }
$workerSettings.network.llm_base_url = $workerSettings.container.desktop_llm_base_url
$workerSettings.streaming.enabled = $true
$workerConfigFile = "config.worker.local.json"
$workerConfigPath = Join-Path $workerRepo $workerConfigFile
$workerJSON = $workerSettings | ConvertTo-Json -Depth 32
$workerConfigHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($workerJSON))).Replace('-','').ToLowerInvariant()
# Public base images do not need the Desktop credential helper, which cannot
# access the Windows credential vault from an OpenSSH logon session.
$workerContext = & $workerDockerExe context show
if ($LASTEXITCODE -ne 0) { throw "Cannot read Docker context." }
$workerDockerEndpoint = & $workerDockerExe context inspect $workerContext --format '{{.Endpoints.docker.Host}}'
if ($LASTEXITCODE -ne 0 -or -not $workerDockerEndpoint) { throw "Cannot resolve Docker engine endpoint." }
$workerClientDirectory = Join-Path $workerRepo ([string]$workerSettings.paths.data_dir + "/docker-client")
Assert-CompanionNotManuallyStopped
New-Item -ItemType Directory -Force $workerClientDirectory | Out-Null
Assert-CompanionNotManuallyStopped
[System.IO.File]::WriteAllText((Join-Path $workerClientDirectory "config.json"), '{"auths":{"https://index.docker.io/v1/":{}}}', [System.Text.UTF8Encoding]::new($false))
$workerDockerPrefix = @("--config", $workerClientDirectory, "--host", $workerDockerEndpoint.Trim())
$workerImage = [string]$workerSettings.container.image
$workerName = [string]$workerSettings.container.name
$workerPort = [int]$workerSettings.servers.worker.port
$workerHubAddress = [System.Net.IPAddress]::Parse([string]$workerSettings.security.robot.hub_source_ipv4).ToString()
$workerMount = "type=bind,source=$workerRepo,target=/config"
$workerGPU = @()
if ($workerSettings.conversation.recognition.device -eq 'cuda') { $workerGPU = @('--gpus', [string]$workerSettings.container.gpu) }
$workerEnv = @("-e", "OMP_NUM_THREADS=$($workerSettings.container.cpu_threads)")
foreach ($workerProvider in @("openclaw", "hermes")) {
    $workerEnv += @("-e", [string]$workerSettings.brains.$workerProvider.api_key_env)
}
Invoke-WorkerDocker -DockerArguments @("build", "-f", "worker/Dockerfile", "-t", $workerImage, ".")
# A name is only a collision lookup, never authority to replace/stop a resource.
$workerExisting = @(Invoke-WorkerDocker -DockerArguments @('ps','-aq','--no-trunc','--filter',"name=^/$workerName$"))
$workerImageID = ([string](Invoke-WorkerDocker -DockerArguments @('image','inspect',$workerImage,'--format','{{.Id}}'))).Trim()
$workerInventory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ReachyCompanion/stop-inventory.local.json'
$workerPythonPrefix = @()
if ([IO.Path]::GetFileName($PythonExecutable) -in @('py','py.exe')) { $workerPythonPrefix=@('-3') }
$workerEnrollArguments = @('-B',"$PSScriptRoot/windows/enroll_worker.py",'--inventory',$workerInventory,
    '--scope-root',$workerRepo,'--docker-executable',$workerDockerExe,'--endpoint',$workerDockerEndpoint.Trim(),
    '--config-sha256',$workerConfigHash)
if ($workerExisting.Count -gt 1) { throw 'Ambiguous worker name collision; no resource was replaced.' }
$workerAlreadyRunning = $false
if ($workerExisting.Count -eq 1) {
    $workerCreatedID = "$($workerExisting[0])".Trim()
    $workerVerifiedJSON = & $PythonExecutable @workerPythonPrefix @workerEnrollArguments --container-id $workerCreatedID --verify-registered --image-id $workerImageID
    if ($LASTEXITCODE -ne 0) { throw 'Worker collision/config/image changed: explicit review or an unused container.name is required. Nothing was removed.' }
    $workerVerified = $workerVerifiedJSON | ConvertFrom-Json
    $workerAlreadyRunning = $workerVerified.running -eq $true
}
Assert-CompanionNotManuallyStopped
[System.IO.File]::WriteAllText($workerConfigPath, $workerJSON, [System.Text.UTF8Encoding]::new($false))
Invoke-WorkerDocker -DockerArguments (@('run','--rm','--mount',$workerMount,'--read-only','--tmpfs','/tmp') + $workerGPU + $workerEnv + @($workerImage,'--config',"/config/$workerConfigFile",'worker','prepare'))
$workerBinding = "$($workerSettings.container.publish_address):${workerPort}:${workerPort}"
if ($workerExisting.Count -eq 0) {
    $workerLaunchID = [Guid]::NewGuid().ToString()
    $workerCreatedID = [string](Invoke-WorkerDocker -DockerArguments (@('create','--name',$workerName,'--restart','unless-stopped',
        '--label',"io.reachy-companion.launch-id=$workerLaunchID",'--label',"io.reachy-companion.scope-root=$workerRepo",
        '-p',$workerBinding,'--mount',$workerMount,'--read-only','--tmpfs','/tmp') + $workerGPU + $workerEnv + @($workerImage,'--config',"/config/$workerConfigFile",'worker','serve')))
    $workerCreatedID=$workerCreatedID.Trim()
    & $PythonExecutable @workerPythonPrefix @workerEnrollArguments --container-id $workerCreatedID --launch-id $workerLaunchID --image-id $workerImageID
    if ($LASTEXITCODE -ne 0) { throw 'Created worker remains stopped: ownership enrollment failed; explicit review required.' }
}
if (-not $workerAlreadyRunning) {
    try {
        Assert-CompanionNotManuallyStopped
        Invoke-WorkerDocker -DockerArguments @('start',$workerCreatedID)
    } finally {
        try { Assert-CompanionNotManuallyStopped }
        catch {
            $workerManualStop = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ReachyCompanion/manual-stop.json'
            & $PythonExecutable @workerPythonPrefix @workerEnrollArguments --container-id $workerCreatedID --image-id $workerImageID --stop-if-latched --latch-path $workerManualStop
            throw 'Manual stop arrived during startup. Only the exact registered worker was eligible for bounded stop; review any incomplete result.'
        }
    }
}
Assert-CompanionNotManuallyStopped
$workerPrincipal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$workerRuleName = [string]$workerSettings.container.windows_firewall_rule
if ($workerPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Assert-CompanionNotManuallyStopped
    Get-NetFirewallRule -DisplayName $workerRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Assert-CompanionNotManuallyStopped
    New-NetFirewallRule -DisplayName $workerRuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $workerPort -RemoteAddress $workerHubAddress -Profile Any | Out-Null
} else {
    Write-Host "To allow hub access, run PowerShell as Administrator and rerun this script."
}
$workerReady = $false
foreach ($workerAttempt in 1..30) {
    try {
        $workerHealth = Invoke-RestMethod -Uri "http://localhost:${workerPort}/health" -TimeoutSec 2
        if ($workerHealth.ok) { $workerReady = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $workerReady) {
    Invoke-WorkerDocker -DockerArguments @("logs", "--tail", "30", $workerName)
    throw "Worker did not become ready. Check the log above."
}
Assert-CompanionNotManuallyStopped
Write-Host "Worker ready."
