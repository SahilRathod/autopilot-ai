param(
    [switch]$Dev,
    [int]$ApiPort = 0,
    [int]$WebPort = 0
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root
if ($ApiPort -eq 0) { $ApiPort = if ($Dev) {8001} else {8000} }
if ($WebPort -eq 0) { $WebPort = if ($Dev) {3001} else {3000} }
if ($ApiPort -lt 1024 -or $ApiPort -gt 65535 -or $WebPort -lt 1024 -or $WebPort -gt 65535 -or $ApiPort -eq $WebPort) {
    throw "Use two different valid local ports."
}
$python = Join-Path $root ".venv\Scripts\python.exe"
$web = Join-Path $root "apps\web"
if (!(Test-Path $python)) { throw "Create .venv and install backend requirements first." }
if (!(Test-Path (Join-Path $web "node_modules"))) { throw "Install web dependencies with npm install first." }
foreach ($command in @("ffmpeg","ffprobe","node","npm.cmd")) {
    if (!(Get-Command $command -ErrorAction SilentlyContinue)) { throw "$command not found on PATH." }
}
foreach ($port in @($ApiPort,$WebPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port already in use. Stop the existing server or choose another port."
    }
}
# A separate checkout/worktree is required for development data isolation.
if ($Dev) { Write-Warning "Use -Dev only in your separate development worktree, never the production checkout." }
$env:AUTOPILOT_API_PORT = "$ApiPort"
& $python -m app.maintenance backup
if ($LASTEXITCODE -ne 0) { throw "Backup failed; startup stopped." }
Push-Location $web
try {
    if (!$Dev) {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Production build failed; startup stopped." }
    }
} finally { Pop-Location }

# Each process inherits the checkout, virtual environment, and configured API port.
$backendCommand = "& '.\.venv\Scripts\python.exe' -m uvicorn apps.api.main:app --host 127.0.0.1 --port $ApiPort --no-access-log"
$workerCommand = "& '.\.venv\Scripts\python.exe' -m app.render_queue"
$mode = if ($Dev) {"dev"} else {"start"}
$webCommand = "npm.cmd run $mode -- --port $WebPort"
Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @("-NoExit","-Command",$backendCommand)
Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @("-NoExit","-Command",$workerCommand)
Start-Process powershell.exe -WorkingDirectory $web -ArgumentList @("-NoExit","-Command",$webCommand)
Write-Host "Dashboard: http://127.0.0.1:$WebPort"
Write-Host "API: http://127.0.0.1:$ApiPort/api/v1/health"
Write-Host "Stop each service with Ctrl+C in its own window."
