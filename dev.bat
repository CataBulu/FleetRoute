@echo off
REM Development mode: starts the API (auto-reload) and the Vite dev server in two windows.
REM Close both windows, or press Ctrl+C in each, to stop.
setlocal
cd /d "%~dp0"
title FleetRoute (dev)

call scripts\setup.bat || (pause & exit /b 1)

echo Starting the API on http://localhost:8000 ...
start "FleetRoute API" cmd /k ".venv\Scripts\python.exe -m uvicorn fleetroute.app:app --app-dir backend --reload --reload-dir backend --port 8000"

echo Starting the web app (it opens in your browser when ready) ...
start "FleetRoute web" cmd /k "npm --prefix frontend run dev -- --open"
