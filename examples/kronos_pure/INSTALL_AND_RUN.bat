@echo off
title KRONOS PURE — 1-Click Installer
color 0A
echo.
echo  ============================================================
echo    KRONOS PURE v2.0 — 1-Click Installer
echo.
echo    [1] Install + Start Bridge
echo    [2] Stop Bridge
echo    [3] Close All KRONOS_PURE Positions
echo    [4] Stop Bridge + Close All
echo.
set /p CHOICE="  Choose (1/2/3/4): "
if "%CHOICE%"=="2" goto :STOP
if "%CHOICE%"=="3" goto :CLOSEALL
if "%CHOICE%"=="4" goto :STOPANDCLOSE
goto :INSTALL

:STOPANDCLOSE
call :STOPBRIDGE
goto :CLOSEALL

:STOP
call :STOPBRIDGE
timeout /t 2 >nul
exit /b 0

:STOPBRIDGE
echo.
echo  Stopping KRONOS PURE Bridge (port 7900)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7900 " ^| findstr "LISTENING"') do (
    echo  Killing PID %%a...
    taskkill /PID %%a /F >nul 2>&1
)
taskkill /FI "WINDOWTITLE eq KRONOS PURE Bridge" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq KRONOS PURE — 1-Click Installer" /F >nul 2>&1
echo  Bridge stopped.
exit /b 0

:CLOSEALL
echo.
echo  Closing all KRONOS_PURE positions via MT5...
python close_all.py
exit /b 0

:INSTALL
echo  ============================================================
echo    30-path Monte Carlo ^| 70%% Confluence ^| M15 Native
echo    AURELIA EMPIRE ^| ZEROEMOTIONS ^| CLAUDE inside
echo  ============================================================
echo.

cd /d "%~dp0"

:: ---------------------------------------------------------------
:: STEP 1 — Python check
:: ---------------------------------------------------------------
echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python not found in PATH.
    echo  Install from https://python.org and re-run.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        Found: %%v

:: ---------------------------------------------------------------
:: STEP 2 — Kronos repo
:: ---------------------------------------------------------------
echo.
echo [2/5] Locating Kronos repo...
if "%KRONOS_PATH%"=="" set KRONOS_PATH=C:\Users\%USERNAME%\Desktop\Kronos
if not exist "%KRONOS_PATH%\model" (
    echo  WARNING: Kronos repo not found at %KRONOS_PATH%
    echo  Set KRONOS_PATH environment variable to your Kronos repo root.
    echo  Example: set KRONOS_PATH=C:\MyFolder\Kronos
    echo  Continuing — bridge will retry on first request.
) else (
    echo        Found: %KRONOS_PATH%
)

:: ---------------------------------------------------------------
:: STEP 3 — Install Python dependencies
:: ---------------------------------------------------------------
echo.
echo [3/5] Installing Python dependencies...
pip install -q flask numpy pandas torch huggingface_hub safetensors einops
if %errorlevel% neq 0 (
    echo  ERROR: pip install failed.
    pause & exit /b 1
)
echo        Done.

:: ---------------------------------------------------------------
:: STEP 4 — Copy EA to all MT5 terminals
:: ---------------------------------------------------------------
echo.
echo [4/5] Copying KRONOS_PURE.mq5 to MT5...
set EA_SRC=%~dp0KRONOS_PURE.mq5
set FOUND=0

if exist "%APPDATA%\MetaQuotes\Terminal" (
    for /d %%T in ("%APPDATA%\MetaQuotes\Terminal\*") do (
        if exist "%%T\MQL5\Experts" (
            copy /Y "%EA_SRC%" "%%T\MQL5\Experts\KRONOS_PURE.mq5" >nul
            echo        Copied to: %%T\MQL5\Experts\
            set FOUND=1
        )
    )
)

if "%FOUND%"=="0" (
    echo  WARNING: No MT5 terminal found automatically.
    echo  Manually copy KRONOS_PURE.mq5 to your MT5 MQL5\Experts\ folder.
) else (
    echo        EA installed successfully.
)

:: ---------------------------------------------------------------
:: STEP 5 — MT5 setup reminder
:: ---------------------------------------------------------------
echo.
echo [5/5] MT5 Setup (do this once):
echo.
echo   a) Open MetaEditor in MT5 (F4)
echo   b) Open KRONOS_PURE.mq5 and press F7 to compile
echo   c) Attach to XAUUSD M15 chart
echo   d) Tools -^> Options -^> Expert Advisors -^> Allowed URLs
echo      Add: http://127.0.0.1:7900
echo   e) Enable live trading (Ctrl+E)
echo.
echo  ============================================================
echo    Starting KRONOS PURE Bridge on http://127.0.0.1:7900
echo    First load takes 30-90s (downloading Kronos-mini)
echo    Press Ctrl+C to stop the bridge
echo  ============================================================
echo.

python kronos_pure_bridge.py
pause
