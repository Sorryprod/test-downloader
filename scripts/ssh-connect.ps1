# Подключение к VPS (Windows PowerShell)
# Использование: .\scripts\ssh-connect.ps1
# Опционально: .\scripts\ssh-connect.ps1 -Command "docker compose ps"

param(
    [string]$Command = ""
)

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

if (-not $hostName -or -not $port -or -not $user) {
    Write-Error "В deploy.env нужны SSH_HOST, SSH_PORT, SSH_USER"
    exit 1
}

$target = "${user}@${hostName}"
Write-Host "SSH $target -p $port"

if ($Command) {
    ssh -p $port $target $Command
} else {
    ssh -p $port $target
}
