@echo off
setlocal
cd /d "%~dp0"
title FleetRoute Optimizer

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERROR] Virtual env not found at .venv\Scripts\streamlit.exe
    pause
    exit /b 1
)

echo Stopping any previous instance...
taskkill /F /IM streamlit.exe 2>nul

echo.
echo ============================================
echo   FleetRoute Optimizer
echo   Opening at http://localhost:8501
echo ============================================
echo.

REM Poll until Streamlit is actually accepting connections, then open browser.
REM curl -s --max-time 1 returns exit 0 only when the server responds.
start "" cmd /c ^
    "for /L %%i in (1,1,30) do (ping -n 2 127.0.0.1 >nul & curl -s --max-time 1 http://localhost:8501 >nul 2>&1 && start http://localhost:8501 && exit)"

REM Run Streamlit (blocks until the user closes the window or Ctrl+C)
".venv\Scripts\streamlit.exe" run main.py ^
    --server.port 8501 ^
    --server.headless true ^
    --browser.gatherUsageStats false ^
    --server.fileWatcherType none

pause
