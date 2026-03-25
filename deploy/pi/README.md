# Flashpoint — Pi Runtime Setup

This directory contains Pi-facing runtime artifacts for Flashpoint on Raspberry Pi OS.

**Transitional:** This is scaffolding for the current PySide6 + FastAPI architecture.
It is not a production installer. See notes on known gaps below.

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
                    └── PySide6 shell launches (FLASHPOINT_MANAGED=1)
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
3. **Python venv created and dependencies installed:**
   ```bash
   cd /home/pi/flashpoint
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   pip install -r desktop/requirements.txt
   ```
4. **`.env` file present** at repo root:
   ```bash
   cp .env.example .env
   # Edit .env: set MOCK_DATA_ENABLED=true and INGEST_SOURCE=mock for initial testing
   ```
5. **Auto-login configured** (see below)

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
# Backend service status
systemctl --user status flashpoint-backend

# Backend health endpoint
curl http://127.0.0.1:8000/api/v1/health

# View backend logs
journalctl --user -u flashpoint-backend -f

# Test the shell launch path manually (without rebooting)
bash scripts/pi_start.sh
```

---

## Known Gaps

### Frontend delivery on Pi is not yet implemented

The Flashpoint shell loads the React/Vite UI from `FLASHPOINT_FRONTEND_URL`. On Pi with
only the backend service running, nothing serves the frontend. The shell will:

1. Connect to the backend successfully (health poll passes)
2. Attempt to load the frontend from its default URL
3. Show "Could not load the frontend" + Retry button

**Interim path for Pi dev/testing:** Use the full orchestrated launcher instead of the
Pi-managed path. This starts the Vite dev server alongside the backend:

```bash
# Full orchestrated mode — starts backend (8001), Vite dev server (5178), and shell:
bash scripts/run.sh
```

**Resolution path:** Once the React app is built (`npm run build`) and FastAPI is
configured to serve `frontend/dist/`, the shell will load cleanly. This is a future
milestone (native shell surfaces / FastAPI static serving).

### Hardware validation not yet done

This scaffolding has been reviewed for correctness on Mac (syntax, path consistency,
config integration) but has not been tested on Pi hardware. The boot → READY flow is
scaffolded but not verified end-to-end.

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

All seam vars are documented in `.env.example` and `desktop/app/config.py`.
