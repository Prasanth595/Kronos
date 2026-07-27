# Activate venv and start the official Kronos Web UI
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
    Write-Error "Virtualenv not found. Create it with: python -m venv .venv"
}

.\.venv\Scripts\Activate.ps1
Write-Host "Starting Kronos Web UI on http://localhost:7070 ..."
Set-Location webui
python run.py
