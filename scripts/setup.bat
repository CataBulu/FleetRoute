@echo off
REM First-run setup shared by dev.bat and run.bat: Python venv + frontend packages.
REM Safe to run again; it skips whatever is already installed.
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Creating the Python environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [ERROR] Python 3.11+ is required. Install it from https://www.python.org/downloads/
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt || exit /b 1
)

where npm >nul 2>&1 || (
    echo [ERROR] Node.js 20.19+ is required. Install it from https://nodejs.org/
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Installing frontend packages...
    call npm --prefix frontend install || exit /b 1
)
exit /b 0
