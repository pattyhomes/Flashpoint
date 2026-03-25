#!/bin/bash
# Flashpoint Pi shell launcher.
#
# Designed for Raspberry Pi OS session autostart via XDG autostart
# (~/.config/autostart/flashpoint.desktop). Can also be run manually
# over SSH to test the Pi boot path.
#
# Launches the Flashpoint desktop shell with Pi-appropriate runtime settings:
#   FLASHPOINT_MANAGED=1    — backend is managed by systemd, not subprocess
#   FLASHPOINT_FULLSCREEN=1 — fullscreen window (Pi Touch Display 2)
#   FLASHPOINT_DEV_QUIT=0   — dev quit shortcut not registered on appliance display
#   FLASHPOINT_BACKEND_HEALTH_URL — explicit 127.0.0.1 to avoid localhost→::1 (IPv6)
#
# The shell's health poller handles backend readiness. This script does not
# wait for the backend — the shell retries automatically if it starts first.
#
# Pi boot sequence (with auto-login and service installed):
#   1. Pi boots → auto-login → systemd --user starts
#   2. flashpoint-backend.service starts (uvicorn on 127.0.0.1:8000)
#   3. Desktop session starts → ~/.config/autostart/flashpoint.desktop runs this script
#   4. Shell polls backend (up to ~20s) → loads React UI → operational
#
# Setup: see deploy/pi/README.md

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export FLASHPOINT_MANAGED=1      # backend managed by systemd — skip subprocess management
export FLASHPOINT_FULLSCREEN=1   # fullscreen for Pi Touch Display 2
export FLASHPOINT_DEV_QUIT=0     # no dev quit shortcut on appliance display

# Explicit 127.0.0.1 — avoids localhost→::1 (IPv6) resolution ambiguity on Linux
export FLASHPOINT_BACKEND_HEALTH_URL=http://127.0.0.1:8000/api/v1/health

exec .venv/bin/python -m desktop.app.launcher
