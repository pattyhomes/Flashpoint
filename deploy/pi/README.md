# Flashpoint — Pi Runtime Setup

This directory contains Pi-facing runtime artifacts for Flashpoint on Raspberry Pi OS.

**Transitional:** This is scaffolding for the current Qt shell + FastAPI architecture.
It is not a production installer. See notes on known gaps below.

**Qt bindings on Pi:** The desktop shell uses system-native PyQt6 on Raspberry Pi OS
(`python3-pyqt6 python3-pyqt6.qtwebengine`) rather than PyQt5 or pip-installed PySide6.
RPi 5 kernels use 16KB memory pages; Qt5 WebEngine's embedded Chromium 87 crashes on boot
with a PartitionAlloc `mmap EINVAL` because it hardcodes 4KB page assumptions. Qt6 WebEngine
(Chromium 102, Debian-patched for 16KB pages) loads correctly. pip-installed PySide6 also
fails on Bookworm due to a `libwebp.so.6` / `.so.7` ABI mismatch.
Mac development continues to use pip-installed PySide6 as before.

---

## What Gets Installed

| Artifact | Source | Installed to |
|---|---|---|
| Backend systemd service | `flashpoint-backend.service` | `~/.config/systemd/user/flashpoint-backend.service` |
| Desktop autostart entry | `flashpoint.desktop` | `~/.config/autostart/flashpoint.desktop` |

The install helper (`install.sh`) substitutes the absolute repo path into both templates.
`scripts/pi_start.sh` (in the repo) is referenced directly by the autostart entry — it is
not copied; the repo must remain at its installed path.

---

## Boot Flow

```
Pi boots
  └── auto-login → pi user session starts
        ├── systemd --user activates
        │     └── flashpoint-backend.service starts
        │           uvicorn app.main:app --host 127.0.0.1 --port 8000
        └── desktop compositor starts
              └── ~/.config/autostart/flashpoint.desktop runs pi_start.sh
                    └── Qt shell launches (FLASHPOINT_MANAGED=1)
                          shell health poller → polls 127.0.0.1:8000 (up to ~20s)
                          → READY: loads React UI in fullscreen webview
```

The shell handles the race between backend startup and shell launch.
If the backend is not yet ready, the shell shows "Connecting…" and retries.
If the backend does not respond within ~20 seconds, the shell shows "Backend not responding"
with a Retry button.

---

## Prerequisites

Before running the install script, ensure:

1. **Raspberry Pi OS 64-bit with desktop** (Bookworm recommended)
2. **Repo is cloned** at a stable path (e.g. `/home/pi/flashpoint`)
3. **System Qt packages installed** (required before creating the venv):
   ```bash
   sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine
   ```
   The shell uses system-native PyQt6 on Pi. PyQt5 crashes on RPi 5 (16KB kernel pages;
   see note above). pip-installed PySide6 has a `libwebp.so.6` / `.so.7` ABI mismatch
   on Bookworm and must NOT be used.

4. **Python venv created with `--system-site-packages`:**

   The venv MUST be created with `--system-site-packages` so the shell can access
   the system-installed PyQt6. A plain venv will NOT work.

   ```bash
   cd /home/pi/flashpoint
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   pip install -e .           # backend deps from pyproject.toml (reads pyproject.toml)
   # Do NOT run: pip install -r desktop/requirements.txt
   # desktop/requirements.txt installs PySide6, which is Mac-only.
   ```

   **Migrating an existing Pi setup:** Delete and recreate the venv to pick up PyQt6:
   ```bash
   rm -rf .venv
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   pip install -e .
   ```
   Or run the migration script: `bash scripts/pi_fix_qt_runtime.sh`
5. **Frontend built** — the backend serves `frontend/dist/` as static files.
   Build it on the Pi (requires Node.js) or build on your Mac and rsync it over.

   **Option A — Build on Pi:**
   ```bash
   # Install Node.js if not already present (one-time):
   sudo apt install -y nodejs npm

   cd /home/pi/flashpoint/frontend && npm install && npm run build
   ```

   **Option B — Build on Mac, rsync to Pi:**
   ```bash
   # On your Mac, from the repo root:
   cd frontend && npm run build
   rsync -a dist/ pi@<pi-host>:/home/pi/flashpoint/frontend/dist/
   ```

   The backend logs a warning at startup if `frontend/dist/` is missing and continues
   to serve the API — the shell will show "Could not load the frontend" until the build
   is present and the backend is restarted.

6. **`.env` file present** at repo root:
   ```bash
   cp .env.example .env
   # Edit .env: set MOCK_DATA_ENABLED=true and INGEST_SOURCE=mock for initial testing
   ```
7. **Auto-login configured** (see below)

### Configuring Auto-Login

Auto-login is a prerequisite for the backend service to start at boot (it runs as a user
service, which requires a user session). Configure via raspi-config:

```bash
sudo raspi-config
# → System Options → Boot / Auto Login → Desktop Autologin
```

---

## Install

```bash
# From the repo root, as the pi user:
bash deploy/pi/install.sh

# Preview without writing anything:
bash deploy/pi/install.sh --dry-run
```

After installation:

```bash
# Enable and start the backend service:
systemctl --user enable flashpoint-backend
systemctl --user start flashpoint-backend

# Verify backend is running:
systemctl --user status flashpoint-backend
curl http://127.0.0.1:8000/api/v1/health
```

The desktop autostart entry takes effect on next login. Log out and back in, or reboot, to test the full boot sequence.

---

## Verifying Each Component

```bash
# Verify Qt bindings are accessible in the venv
.venv/bin/python -c "from desktop.app.qt_compat import QApplication, QWebEngineView, Signal; print('Qt OK')"

# Backend service status
systemctl --user status flashpoint-backend

# Backend health endpoint
curl http://127.0.0.1:8000/api/v1/health

# Frontend static serving (returns HTML if frontend/dist/ was built)
curl -s http://127.0.0.1:8000/ | head -4

# View backend logs
journalctl --user -u flashpoint-backend -f

# Test the shell launch path manually (without rebooting)
bash scripts/pi_start.sh
```

---

## Known Gaps

### Frontend delivery — resolved at code level, hardware not yet validated

The backend now serves `frontend/dist/` as static files via FastAPI `StaticFiles`. The
shell's `FLASHPOINT_FRONTEND_URL=http://127.0.0.1:8000` (set by `pi_start.sh`) points
at the backend root. This path is implemented and Mac-validated.

**Remaining requirement:** `frontend/dist/` must be built before the backend starts.
See the "Build the frontend" step in Prerequisites above. If the build is missing, the
backend warns at startup and the shell shows "Could not load the frontend" — the existing
graceful degradation path.

### Hardware validation not yet done

This scaffolding and the frontend delivery path have been reviewed for correctness on Mac
but have not been tested on Pi hardware. The boot → READY flow is implemented but not
verified end-to-end on physical hardware.

---

## Uninstall

```bash
# Stop and disable the backend service
systemctl --user stop flashpoint-backend
systemctl --user disable flashpoint-backend

# Remove installed files
rm -f ~/.config/systemd/user/flashpoint-backend.service
rm -f ~/.config/autostart/flashpoint.desktop

# Reload systemd user daemon
systemctl --user daemon-reload
```

---

## Pi Seam Env Vars (set by `scripts/pi_start.sh`)

| Env var | Value | Purpose |
|---|---|---|
| `FLASHPOINT_MANAGED` | `1` | Launcher skips subprocess management; backend is from systemd |
| `FLASHPOINT_FULLSCREEN` | `1` | Shell opens fullscreen (`showFullScreen()`) |
| `FLASHPOINT_DEV_QUIT` | `0` | Custom `QShortcut` (Ctrl+Q) not registered |
| `FLASHPOINT_BACKEND_HEALTH_URL` | `http://127.0.0.1:8000/api/v1/health` | Explicit IPv4 — avoids `localhost`→`::1` ambiguity |
| `FLASHPOINT_FRONTEND_URL` | `http://127.0.0.1:8000` | Backend serves frontend/dist/ at root — same host:port |

All seam vars are documented in `.env.example` and `desktop/app/config.py`.
