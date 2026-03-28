#!/bin/bash
# Flashpoint — Pi Qt Runtime Migration
#
# Fixes the desktop shell runtime environment on Raspberry Pi OS Bookworm.
# Run this after pulling changes that switched the shell to system-native PyQt6.
#
# Why PyQt6:
#   RPi 5 kernels use 16KB memory pages. Qt5 WebEngine's Chromium 87 crashes on
#   boot with a PartitionAlloc mmap EINVAL because it hardcodes 4KB assumptions.
#   Qt6 WebEngine (Debian Bookworm, patched for 16KB pages) loads correctly.
#
# What this script does:
#   1. Installs python3-pyqt6 and python3-pyqt6.qtwebengine via apt
#   2. Deletes the existing .venv (which may have pip-installed PySide6 or PyQt5)
#   3. Recreates .venv with --system-site-packages (required for system PyQt6)
#   4. Reinstalls backend Python deps (pip install -e .)
#   5. Verifies the Qt compat layer imports correctly
#
# Usage:
#   bash scripts/pi_fix_qt_runtime.sh          # interactive (asks before deleting .venv)
#   bash scripts/pi_fix_qt_runtime.sh --yes    # non-interactive (skip confirmation)
#
# This script does NOT:
#   - install systemd/autostart files  (use: bash deploy/pi/install.sh)
#   - build the frontend               (use: cd frontend && npm run build)
#   - modify .env
#   - touch Mac dependencies
#
# See deploy/pi/README.md for the full Pi setup guide.

set -euo pipefail

# ── Flag parsing ───────────────────────────────────────────────────────────────

YES=0
for arg in "$@"; do
    case "$arg" in
        --yes) YES=1 ;;
        *) echo "Unknown argument: $arg"; echo "Usage: $0 [--yes]"; exit 1 ;;
    esac
done

# ── Repo root ──────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── Platform check ─────────────────────────────────────────────────────────────

if [ "$(uname -s)" != "Linux" ]; then
    echo "Error: this script is intended for Raspberry Pi OS (Linux only)."
    echo
    echo "On Mac, install the desktop shell dependencies with:"
    echo "  pip install -r desktop/requirements.txt"
    exit 1
fi

# ── Tool checks ────────────────────────────────────────────────────────────────

for cmd in python3 apt; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: '$cmd' not found. Is this Raspberry Pi OS?"
        exit 1
    fi
done

# ── Header ─────────────────────────────────────────────────────────────────────

echo "Flashpoint — Pi Qt Runtime Migration"
echo "====================================="
echo "Repo root: $REPO_ROOT"
echo
echo "This script will:"
echo "  1. sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine"
echo "  2. Delete $REPO_ROOT/.venv"
echo "  3. Recreate .venv with --system-site-packages"
echo "  4. pip install -e .  (backend deps)"
echo "  5. Verify Qt compat layer"
echo

# ── Confirm ────────────────────────────────────────────────────────────────────

if [ "$YES" = "0" ]; then
    if [ -d ".venv" ]; then
        echo "WARNING: .venv will be deleted and recreated. This cannot be undone."
        echo "Pass --yes to skip this prompt."
        echo
        read -r -p "Continue? [y/N] " REPLY
        case "$REPLY" in
            [yY]|[yY][eE][sS]) ;;
            *) echo "Aborted."; exit 1 ;;
        esac
        echo
    fi
fi

# ── Step 1: System Qt packages ─────────────────────────────────────────────────

echo ">>> Installing system PyQt6 packages..."
sudo apt install -y python3-pyqt6 python3-pyqt6.qtwebengine
echo "    Done."
echo

# ── Step 2: Remove old venv ────────────────────────────────────────────────────

if [ -d ".venv" ]; then
    echo ">>> Removing old .venv..."
    rm -rf .venv
    echo "    Done."
    echo
fi

# ── Step 3: Create new venv with system-site-packages ─────────────────────────

echo ">>> Creating .venv with --system-site-packages..."
python3 -m venv --system-site-packages .venv
echo "    Done."
echo

# ── Step 4: Install backend deps ───────────────────────────────────────────────

echo ">>> Upgrading pip..."
.venv/bin/pip install --upgrade pip --quiet
echo "    Done."
echo

echo ">>> Installing backend dependencies (pip install -e .)..."
.venv/bin/pip install -e .
echo "    Done."
echo

# ── Step 5: Verify Qt compat layer ─────────────────────────────────────────────

echo ">>> Verifying Qt compat layer..."
if .venv/bin/python -c "from desktop.app.qt_compat import QApplication, QWebEngineView, Signal; print('    Qt compat: OK')"; then
    :
else
    echo
    echo "ERROR: Qt compat layer verification failed."
    echo "Check that python3-pyqt6.qtwebengine was installed successfully:"
    echo "  python3 -c 'from PyQt6.QtWebEngineWidgets import QWebEngineView; print(\"OK\")'"
    exit 1
fi
echo

# ── Done ───────────────────────────────────────────────────────────────────────

echo "====================================="
echo "Migration complete."
echo
echo "Next steps:"
echo
echo "1. Verify the shell launches:"
echo "   bash scripts/pi_start.sh"
echo
echo "2. If the backend service is running, restart it to pick up any backend changes:"
echo "   systemctl --user restart flashpoint-backend"
echo
echo "3. Verify the backend is healthy:"
echo "   curl http://127.0.0.1:8000/api/v1/health"
