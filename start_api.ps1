# Activate venv and start the local Kronos candle prediction API
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
    Write-Error "Virtualenv not found. Create it with: python -m venv .venv"
}

.\.venv\Scripts\Activate.ps1
Write-Host "Starting Kronos API on http://127.0.0.1:8000 ..."
Write-Host "Docs: http://127.0.0.1:8000/docs"
Set-Location app
uvicorn main:app --host 127.0.0.1 --port 8000
