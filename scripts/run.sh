#!/bin/bash
# Flashpoint — one-command desktop launcher (development / Mac).
#
# Starts backend (port 8001), frontend dev server (port 5178), and the
# PySide6 desktop shell together with proper readiness sequencing.
# All three processes are cleaned up when the shell exits (Ctrl+Q) or
# when this terminal receives Ctrl+C.
#
# Prerequisites: .venv with PySide6 + uvicorn, Node.js / npm, .env file
#   pip install -r backend/requirements.txt desktop/requirements.txt
#   cp .env.example .env
#
# TRANSITIONAL: subprocess orchestration for local dev.
# Pi production: set FLASHPOINT_MANAGED=1 and launch via desktop autostart
# or systemd user service — backend/frontend are managed externally.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f ".venv/bin/python" ]; then
    echo "Error: .venv not found."
    echo "Run: python3 -m venv .venv && source .venv/bin/activate"
    echo "     pip install -r backend/requirements.txt desktop/requirements.txt"
    exit 1
fi

exec .venv/bin/python -m desktop.app.launcher
