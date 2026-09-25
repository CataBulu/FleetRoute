@echo off
REM Production mode: builds the interface once, then serves app + API on http://localhost:8000.
setlocal
cd /d "%~dp0"
title FleetRoute

call scripts\setup.bat || (pause & exit /b 1)

if not exist "frontend\dist\index.html" (
    echo Building the web interface...
    call npm --prefix frontend run build || (pause & exit /b 1)
)

echo.
echo ============================================
echo   FleetRoute is running at http://localhost:8000
echo   Close this window or press Ctrl+C to stop it.
echo ============================================
echo.

REM Open the browser once the server answers its health check.
start "" /b cmd /c "for /L %%i in (1,1,40) do (ping -n 2 127.0.0.1 >nul & curl -s --max-time 1 http://localhost:8000/api/health >nul 2>&1 && start http://localhost:8000 && exit)"

".venv\Scripts\python.exe" -m uvicorn fleetroute.app:app --app-dir backend --host 127.0.0.1 --port 8000
pause
