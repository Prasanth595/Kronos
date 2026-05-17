$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$backend = Join-Path $root "webui"
$frontend = Join-Path $root "webui-next"

function Test-Command($name) {
    $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-PortInUse($port) {
    $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $null -ne $connection
}

if (-not (Test-Command "python")) {
    Write-Host "Python was not found on PATH. Install Python or add it to PATH first." -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Command "npm")) {
    Write-Host "npm was not found on PATH. Install Node.js or add npm to PATH first." -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path -LiteralPath $backend)) {
    Write-Host "Backend directory was not found: $backend" -ForegroundColor Red
    pause
    exit 1
}

if (-not (Test-Path -LiteralPath $frontend)) {
    Write-Host "Frontend directory was not found: $frontend" -ForegroundColor Red
    pause
    exit 1
}

if (Test-PortInUse 7070) {
    Write-Host "Backend API is already running on http://localhost:7070"
} else {
    Write-Host "Starting Kronos backend API on http://localhost:7070 ..."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location -LiteralPath '$backend'; python app.py"
    ) -WindowStyle Normal
}

Start-Sleep -Seconds 4

if (Test-PortInUse 3000) {
    Write-Host "Web UI is already running on http://localhost:3000"
} else {
    Write-Host "Starting Kronos web UI on http://localhost:3000 ..."
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location -LiteralPath '$frontend'; npm run dev -- --hostname 0.0.0.0 --port 3000"
    ) -WindowStyle Normal
}

Start-Sleep -Seconds 6
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Kronos is starting." -ForegroundColor Green
Write-Host "Keep the two PowerShell windows open while you use the app."
Write-Host "Close those two windows when you want to stop it."
Write-Host ""
pause
