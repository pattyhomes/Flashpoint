#!/bin/bash
# Flashpoint Pi install helper.
#
# Installs the backend systemd user service and desktop session autostart entry
# into standard user-config locations on Raspberry Pi OS.
#
# Usage:
#   bash deploy/pi/install.sh           # install
#   bash deploy/pi/install.sh --dry-run # show what would be installed, write nothing
#
# Run as the pi user from any directory. The repo root is detected from this
# script's own location. No root / sudo required.
#
# What gets installed:
#   ~/.config/systemd/user/flashpoint-backend.service
#   ~/.config/autostart/flashpoint.desktop
#
# After installing:
#   systemctl --user enable flashpoint-backend
#   systemctl --user start flashpoint-backend
#   Log out and back in (or reboot) to activate the desktop autostart entry.
#
# See deploy/pi/README.md for the full setup guide.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DRY_RUN=0

if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
    echo "[dry-run] No files will be written."
    echo
fi

echo "Repo root: $REPO_ROOT"
echo

# ── Prerequisites ─────────────────────────────────────────────────────────────

if [ ! -f "$REPO_ROOT/.venv/bin/python" ]; then
    echo "Error: .venv not found at $REPO_ROOT/.venv"
    echo "Run on Pi:"
    echo "  sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine"
    echo "  python3 -m venv --system-site-packages .venv"
    echo "  source .venv/bin/activate && pip install -e ."
    echo "See deploy/pi/README.md for full setup instructions."
    exit 1
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "Error: .env not found at $REPO_ROOT/.env"
    echo "Run: cp .env.example .env  (then edit as needed for Pi)"
    exit 1
fi

# ── Install systemd user service ──────────────────────────────────────────────

SERVICE_SRC="$SCRIPT_DIR/flashpoint-backend.service"
SERVICE_DST="$HOME/.config/systemd/user/flashpoint-backend.service"

echo "Backend service:"
echo "  source : $SERVICE_SRC"
echo "  install: $SERVICE_DST"

if [ "$DRY_RUN" = "1" ]; then
    echo
    echo "  [dry-run] Substituted content:"
    echo "  ---"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$SERVICE_SRC" | sed 's/^/  /'
    echo "  ---"
else
    mkdir -p "$HOME/.config/systemd/user"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$SERVICE_SRC" > "$SERVICE_DST"
    echo "  Written."
fi
echo

# ── Install desktop autostart entry ───────────────────────────────────────────

DESKTOP_SRC="$SCRIPT_DIR/flashpoint.desktop"
DESKTOP_DST="$HOME/.config/autostart/flashpoint.desktop"

echo "Desktop autostart:"
echo "  source : $DESKTOP_SRC"
echo "  install: $DESKTOP_DST"

if [ "$DRY_RUN" = "1" ]; then
    echo
    echo "  [dry-run] Substituted content:"
    echo "  ---"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$DESKTOP_SRC" | sed 's/^/  /'
    echo "  ---"
else
    mkdir -p "$HOME/.config/autostart"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$DESKTOP_SRC" > "$DESKTOP_DST"
    echo "  Written."
fi
echo

# ── Install desktop launcher icon ─────────────────────────────────────────────

LAUNCHER_SRC="$SCRIPT_DIR/Flashpoint-launcher.desktop"
LAUNCHER_DST="$HOME/Desktop/Flashpoint.desktop"

echo "Desktop launcher icon:"
echo "  source : $LAUNCHER_SRC"
echo "  install: $LAUNCHER_DST"

if [ "$DRY_RUN" = "1" ]; then
    echo
    echo "  [dry-run] Substituted content:"
    echo "  ---"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$LAUNCHER_SRC" | sed 's/^/  /'
    echo "  ---"
else
    mkdir -p "$HOME/Desktop"
    sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$LAUNCHER_SRC" > "$LAUNCHER_DST"
    chmod +x "$LAUNCHER_DST"
    echo "  Written and marked executable."
fi
echo

# ── Next steps ────────────────────────────────────────────────────────────────

if [ "$DRY_RUN" = "1" ]; then
    echo "[dry-run] Done. Run without --dry-run to write files."
else
    echo "Installation complete. Next steps:"
    echo
    echo "1. Enable auto-login if not already configured:"
    echo "   sudo raspi-config"
    echo "   → System Options → Boot / Auto Login → Desktop Autologin"
    echo
    echo "2. Enable and start the backend service:"
    echo "   systemctl --user enable flashpoint-backend"
    echo "   systemctl --user start flashpoint-backend"
    echo
    echo "3. Verify the backend is running:"
    echo "   systemctl --user status flashpoint-backend"
    echo "   curl http://127.0.0.1:8000/api/v1/health"
    echo
    echo "4. The desktop autostart entry takes effect on next login."
    echo "   Log out and back in (or reboot) to test."
    echo
    echo "Note: Ensure frontend/dist/ is built before starting the backend."
    echo "  cd frontend && npm run build"
    echo "If not built, the backend serves the API only and the shell will show"
    echo "'Could not load the frontend'. See deploy/pi/README.md for details."
fi
