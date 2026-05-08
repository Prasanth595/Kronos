@echo off
title KRONOS EDGE Bridge
echo ============================================================
echo   KRONOS EDGE Bridge v1.0
echo   AURELIA EMPIRE ^| ZEROEMOTIONS ^| CLAUDE inside
echo ============================================================
echo.

:: Go to the script's directory
cd /d "%~dp0"

:: Install dependencies if needed
echo [1/3] Checking dependencies...
pip install -q -r requirements_edge.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python is in PATH.
    pause
    exit /b 1
)
echo       Done.

:: Pre-warm model in background using a quick ping after startup
echo [2/3] Starting bridge on http://127.0.0.1:7800 ...
echo       (First startup loads the Kronos model - takes 30-90s)
echo.
echo [3/3] MT5 Setup reminder:
echo       - Copy KRONOS_EDGE.mq5 to your MT5 Experts/ folder
echo       - Compile in MetaEditor (F7)
echo       - Add http://127.0.0.1:7800 to Allowed URLs
echo         (Tools -^> Options -^> Expert Advisors -^> Allowed URLs)
echo.
echo Press Ctrl+C to stop the bridge.
echo ============================================================
echo.

python kronos_edge_bridge.py
pause
