#!/bin/bash
# Apply Flashpoint's Raspberry Pi Touch Display 2 portrait touch calibration.
#
# Symptom fixed:
#   Display is rotated by labwc/wlr-randr, but Goodix touch coordinates remain
#   identity-mapped, so taps land in the wrong place and desktop selection boxes
#   appear away from the finger.
#
# This installs a libinput hwdb calibration matrix for the Goodix touchscreen.
# A reboot or session restart is recommended after running.
set -e

HWDB_FILE="/etc/udev/hwdb.d/99-flashpoint-goodix-touch.hwdb"

sudo tee "$HWDB_FILE" >/dev/null <<'EOF'
# Flashpoint Pi Touch Display 2 portrait calibration.
# DSI-2 is rotated right/270 by the Wayland compositor; rotate Goodix touch coordinates to match.
evdev:name:Goodix Capacitive TouchScreen:*
 LIBINPUT_CALIBRATION_MATRIX=0 1 0 -1 0 1
EOF

sudo systemd-hwdb update
sudo udevadm trigger -s input

echo "Installed $HWDB_FILE"
echo
udevadm info -q property -n /dev/input/event5 2>/dev/null \
  | grep -E 'DEVNAME|LIBINPUT_CALIBRATION_MATRIX|ID_INPUT_TOUCHSCREEN' \
  || true
echo
echo "Reboot or restart the desktop session for labwc/libinput to fully pick up the calibration."
