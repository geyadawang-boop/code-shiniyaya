@echo off
chcp 65001 >nul 2>&1
title BiliSum v7.1 · B站视频总结工具
echo.
echo   BiliSum v7.1 - B站视频总结工具
echo   http://localhost:8000
echo.

set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

:: Only run bootstrap on first launch (when bootstrap_success.json is missing)
if exist bootstrap_success.json (
    echo [BiliSum] Already bootstrapped, skipping checks...
    goto skip_bootstrap
)

echo [BiliSum] First launch — running bootstrap (one-time setup)...
python bootstrap.py
if %ERRORLEVEL% NEQ 0 (
    echo [BiliSum] Bootstrap failed with critical errors, see above.
    echo [BiliSum] Starting anyway — some features may not work.
)
echo.

:skip_bootstrap

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH. Please install Python 3.10+
    pause
    exit /b 1
)

:: Kill any existing BiliSum backend process first
echo [0] Cleaning up old backend processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
ping 127.0.0.1 -n 2 >nul

:: Start FastAPI backend
echo [1/2] Starting backend server...
start "BiliSum-Backend" /MIN python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

:: Wait for backend to be ready
echo [*] Waiting for backend...
set "retry=0"
:wait_backend
ping 127.0.0.1 -n 3 >nul
python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/docs',timeout=5); exit(0 if r.status_code==200 else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend ready on http://127.0.0.1:8000
    goto backend_ready
)
set /a retry+=1
if %retry% lss 20 (
    echo [*] Retry %retry%/20...
    goto wait_backend
)
echo [WARN] Backend may not be ready, starting Electron anyway...

:backend_ready
:: Start Electron
echo [2/2] Starting Electron...
npx electron main.js

:: Cleanup on exit
echo.
echo BiliSum closed. Press any key to close this window.
pause >nul
