param([string]$Configuration = "config.local.json")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$workerRepo = Split-Path -Parent $PSScriptRoot
Set-Location $workerRepo
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required. Start it with Linux containers."
}
function Invoke-WorkerDocker {
    param([string[]]$DockerArguments)
    $previousDockerConfig = $env:DOCKER_CONFIG
    try {
        $env:DOCKER_CONFIG = $workerClientDirectory
        & docker @workerDockerPrefix @DockerArguments
        if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($DockerArguments[0])" }
    } finally { $env:DOCKER_CONFIG = $previousDockerConfig }
}
$workerDockerOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $workerDockerOS.Trim() -ne "linux") {
    throw "Start Docker Desktop with Linux containers before running this script."
}
$workerConfigSource = Join-Path $workerRepo $Configuration
. "$PSScriptRoot/common.ps1"
$workerSettings = Read-CompanionSettings $workerConfigSource
$workerTokenFile = Join-Path $workerRepo $workerSettings.paths.token_file
if (-not (Test-Path $workerTokenFile)) { throw "Copy the existing secrets/token from your Mac repository." }
if ((Get-Content -Raw $workerTokenFile).Trim().Length -lt 32) { throw "Invalid companion token." }
$workerSettings.network.llm_base_url = $workerSettings.container.desktop_llm_base_url
$workerSettings.streaming.enabled = $true
$workerConfigFile = "config.worker.local.json"
$workerConfigPath = Join-Path $workerRepo $workerConfigFile
$workerJSON = $workerSettings | ConvertTo-Json -Depth 32
[System.IO.File]::WriteAllText($workerConfigPath, $workerJSON, [System.Text.UTF8Encoding]::new($false))
# Public base images do not need the Desktop credential helper, which cannot
# access the Windows credential vault from an OpenSSH logon session.
$workerContext = & docker context show
if ($LASTEXITCODE -ne 0) { throw "Cannot read Docker context." }
$workerDockerEndpoint = & docker context inspect $workerContext --format '{{.Endpoints.docker.Host}}'
if ($LASTEXITCODE -ne 0 -or -not $workerDockerEndpoint) { throw "Cannot resolve Docker engine endpoint." }
$workerClientDirectory = Join-Path $workerRepo ([string]$workerSettings.paths.data_dir + "/docker-client")
New-Item -ItemType Directory -Force $workerClientDirectory | Out-Null
[System.IO.File]::WriteAllText((Join-Path $workerClientDirectory "config.json"), '{"auths":{"https://index.docker.io/v1/":{}}}', [System.Text.UTF8Encoding]::new($false))
$workerDockerPrefix = @("--config", $workerClientDirectory, "--host", $workerDockerEndpoint.Trim())
$workerImage = [string]$workerSettings.container.image
$workerName = [string]$workerSettings.container.name
$workerPort = [int]$workerSettings.servers.worker.port
$workerHubAddress = [System.Net.IPAddress]::Parse([string]$workerSettings.security.robot.hub_source_ipv4).ToString()
$workerMount = "type=bind,source=$workerRepo,target=/config"
$workerEnv = @("-e", "OMP_NUM_THREADS=$($workerSettings.container.cpu_threads)")
foreach ($workerProvider in @("openclaw", "hermes")) {
    $workerEnv += @("-e", [string]$workerSettings.brains.$workerProvider.api_key_env)
}
Invoke-WorkerDocker -DockerArguments @("build", "-f", "worker/Dockerfile", "-t", $workerImage, ".")
Invoke-WorkerDocker -DockerArguments (@("run", "--rm", "--mount", $workerMount, "--read-only", "--tmpfs", "/tmp") + $workerEnv + @($workerImage, "--config", "/config/$workerConfigFile", "worker", "prepare"))
# Only replace our named container. Model files and configuration stay on disk.
$workerExisting = & docker ps -a --filter "name=^/$workerName$" --format '{{.Names}}'
if ($LASTEXITCODE -ne 0) { throw "Cannot list Docker containers." }
if ($workerExisting -contains $workerName) {
    Invoke-WorkerDocker -DockerArguments @("rm", "-f", $workerName)
}
$workerBinding = "$($workerSettings.container.publish_address):${workerPort}:${workerPort}"
Invoke-WorkerDocker -DockerArguments (@("run", "-d", "--name", $workerName, "--restart", "unless-stopped", "-p", $workerBinding, "--mount", $workerMount, "--read-only", "--tmpfs", "/tmp") + $workerEnv + @($workerImage, "--config", "/config/$workerConfigFile", "worker", "serve"))
$workerPrincipal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$workerRuleName = [string]$workerSettings.container.windows_firewall_rule
if ($workerPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Get-NetFirewallRule -DisplayName $workerRuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
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
Write-Host "Worker ready."
