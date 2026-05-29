# Kronos - Startup Script
# Starts the Web UI on a random port, using Python with CUDA support

param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Kronos - Startup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# If a venv is active, deactivate it to avoid using the wrong Python
if ($env:VIRTUAL_ENV) {
    Write-Host "[INFO] Deactivating venv '$env:VIRTUAL_ENV' ..." -ForegroundColor Yellow
    & deactivate 2>$null
    # Manually clear venv variables from this session's PATH
    $env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notlike "$env:VIRTUAL_ENV*" }) -join ';'
    Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:\VIRTUAL_ENV_PROMPT -ErrorAction SilentlyContinue
}

# Find Python with CUDA support (search all instances in PATH)
$pythonExe = $null
$candidatos = (where.exe python 2>$null) -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" -and (Test-Path $_) }

foreach ($cand in $candidatos) {
    $result = & $cand -c "import torch; print(torch.cuda.is_available())" 2>$null
    if ($result -eq "True") {
        $pythonExe = $cand
        break
    }
}

if (-not $pythonExe) {
    # Fallback: accept CPU if no CUDA found
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $pythonExe) {
        Write-Host "[ERROR] Python not found in PATH. Install Python 3.10+ and try again." -ForegroundColor Red
        exit 1
    }
    Write-Host "[WARNING] Python with CUDA not found. Using CPU: $pythonExe" -ForegroundColor Yellow
    Write-Host "        Para CUDA, instale: pip install torch --index-url https://download.pytorch.org/whl/cu128" -ForegroundColor Yellow
} else {
    $pyVersion = & $pythonExe --version 2>&1
    $gpuName   = & $pythonExe -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
    Write-Host "[OK] $pyVersion  |  CUDA - $gpuName" -ForegroundColor Green
    Write-Host "[OK] Python: $pythonExe" -ForegroundColor Green
}

# Project root directory
$projectRoot = $PSScriptRoot
Set-Location $projectRoot

# Install dependencies
if (-not $SkipInstall) {
    Write-Host "[...] Installing project dependencies ..." -ForegroundColor Yellow
    & $pythonExe -m pip install -r (Join-Path $projectRoot "requirements.txt") --quiet

    $webuiReqs = Join-Path $projectRoot "webui\requirements.txt"
    if (Test-Path $webuiReqs) {
        Write-Host "[...] Installing Web UI dependencies ..." -ForegroundColor Yellow
        & $pythonExe -m pip install -r $webuiReqs --quiet
    }
    Write-Host "[OK] Dependencies installed." -ForegroundColor Green
} else {
    Write-Host "[SKIP] Dependency installation skipped (-SkipInstall)." -ForegroundColor Yellow
}

# Generate random port between 10000 and 60000 (avoids well-known ports)
$port = Get-Random -Minimum 10000 -Maximum 60000
for ($i = 0; $i -lt 10; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue)) { break }
    $port = Get-Random -Minimum 10000 -Maximum 60000
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Kronos Web UI" -ForegroundColor Cyan
Write-Host "  Port  : $port" -ForegroundColor Cyan
Write-Host "  URL   : http://localhost:$port" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

# Open browser automatically after a few seconds
Start-Job -ScriptBlock {
    param($url)
    Start-Sleep -Seconds 3
    Start-Process $url
} -ArgumentList "http://localhost:$port" | Out-Null

# Start Flask on the random port
Set-Location (Join-Path $projectRoot "webui")
$env:FLASK_APP = "app.py"

& $pythonExe -c @"
import sys, os
sys.path.insert(0, '..')
from webui.app import app
app.run(debug=False, host='127.0.0.1', port=$port)
"@
