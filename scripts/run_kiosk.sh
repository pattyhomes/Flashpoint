#!/bin/bash
# Flashpoint — one-command fullscreen/kiosk launcher.
#
# This app's production display path is the Qt desktop shell, not Chromium
# kiosk mode. This script keeps the normal dev process orchestration from
# scripts/run.sh, but forces the shell into fullscreen with no window chrome.
#
# Quit remains available for development via Command+Q / Ctrl+Q and the shell's
# dev close affordance unless FLASHPOINT_DEV_QUIT=0 is exported by the caller.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export FLASHPOINT_FULLSCREEN="${FLASHPOINT_FULLSCREEN:-1}"
export FLASHPOINT_DEV_QUIT="${FLASHPOINT_DEV_QUIT:-1}"

exec bash scripts/run.sh
