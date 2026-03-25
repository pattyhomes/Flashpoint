#!/bin/bash
# Launch the Flashpoint desktop shell (development mode).
#
# Requires backend and frontend already running in separate terminals:
#   Terminal 1: bash scripts/dev_backend.sh
#   Terminal 2: cd frontend && npm run dev
#
# The shell polls the backend health endpoint, then loads the frontend
# (http://localhost:5173) inside a fullscreen QWebEngineView.
#
# Quit: Ctrl+Q
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f ".venv/bin/python" ]; then
    echo "Error: .venv not found. Run: python3 -m venv .venv && source .venv/bin/activate"
    exit 1
fi

exec .venv/bin/python -m desktop.app.main
