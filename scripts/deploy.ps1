# Деплой на VPS из Windows PowerShell
# Использование: .\scripts\deploy.ps1

$ErrorActionPreference = "Stop"

$EnvFile = Join-Path $PSScriptRoot "deploy.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Создай scripts\deploy.env из deploy.env.example"
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $name, $value = $_ -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value.Trim()
}

$hostName = $env:SSH_HOST
$port = $env:SSH_PORT
$user = $env:SSH_USER
$remoteDir = if ($env:REMOTE_APP_DIR) { $env:REMOTE_APP_DIR } else { "/opt/files-downloader" }
$appPort = if ($env:APP_HOST_PORT) { $env:APP_HOST_PORT } else { "8088" }

if (-not $hostName -or -not $port -or -not $user) {
    Write-Error "В deploy.env нужны SSH_HOST, SSH_PORT, SSH_USER"
    exit 1
}

$target = "${user}@${hostName}"
Write-Host "==> Deploy to ${target}:${port} (${remoteDir})"

$remoteScript = @"
set -euo pipefail
cd '$remoteDir'
git pull --ff-only
export APP_HOST_PORT='$appPort'
docker compose up -d --build
docker compose ps
echo 'OK: http://${hostName}:${appPort}'
"@

$remoteScript | ssh -p $port $target bash

Write-Host "==> Done"
