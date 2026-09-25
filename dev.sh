#!/usr/bin/env bash
# Development mode on macOS / Linux: API with auto-reload plus the Vite dev server.
# Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Creating the Python environment..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r backend/requirements-dev.txt
fi
[ -d frontend/node_modules ] || npm --prefix frontend install

.venv/bin/python -m uvicorn fleetroute.app:app --app-dir backend --reload --reload-dir backend --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null' EXIT

npm --prefix frontend run dev -- --open
