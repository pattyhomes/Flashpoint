# Flashpoint Desktop Shell

## Architecture

**Transitional hybrid.** The desktop shell wraps the existing React/Vite frontend
in a PySide6 fullscreen window via `QWebEngineView`. The FastAPI backend and React
frontend are unchanged — the shell contributes:

- Fullscreen native window, no browser chrome
- Native loading / connecting state before the web UI is ready
- Native backend-unavailable / retry state
- Lifecycle ownership of the application window

This is the intentional near-term architecture, not a permanent compromise. Over time,
selected surfaces (status bar, startup screen, settings) will move to native Qt widgets.
The map and event feed will remain web-rendered.

```
PySide6 Shell (fullscreen)
└── QWebEngineView ← React/Vite frontend (localhost:5178 in orchestrated dev)
                       └── /api/* proxied to FastAPI backend (localhost:8001)
```

---

## Dev Setup (Mac)

**Prerequisites:** Python 3.11+, Node.js 18+, existing repo venv at `.venv/`

### 1. Install dependencies

```bash
# From the repo root
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r desktop/requirements.txt
cp .env.example .env   # if not already done
```

PySide6 is ~400MB. Install once; it sits in `.venv/`.

### 2. Verify PySide6

```bash
.venv/bin/python -c "
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
print('PySide6 OK')
"
```

### 3. Run (one command)

```bash
bash scripts/run.sh
```

This starts backend (port 8001), frontend dev server (port 5178), and the PySide6
shell together. Readiness is verified before each step. All processes clean up when
the shell exits.

**Quit:** `Command+Q` (macOS) / `Ctrl+Q` (Windows/Linux) in the shell window, or `Ctrl+C` in the terminal.

---

## Managed Ports

The orchestrated path uses dedicated ports to avoid collisions with standalone dev sessions:

| Service | Orchestrated (`run.sh`) | Standalone |
|---|---|---|
| Backend | 8001 | 8000 |
| Frontend | 5178 | 5173 |

The shell reads its URLs from `FLASHPOINT_BACKEND_HEALTH_URL` and `FLASHPOINT_FRONTEND_URL`
env vars (set by the launcher before importing the shell). Standalone `dev_desktop.sh`
sets no env vars, so the shell falls back to the 8000/5173 defaults.

---

## Shell Behavior

| State | What the operator sees |
|---|---|
| Starting / backend not yet ready | Dark screen — "FLASHPOINT / Connecting…" |
| Backend not responding after ~20s | Dark screen — status message + "Retry" button |
| Backend ready, frontend loading | Dark screen — still "Connecting…" (avoids blank flash) |
| Frontend URL unreachable / load error | Dark screen — "Could not load the frontend" + "Retry" button |
| Operational | React UI fullscreen, no chrome |

The shell only reveals the webview after a successful frontend load (`loadFinished(True)`).
A failed frontend load remains a native overlay-owned state — the operator always sees a
shell-controlled surface, never a blank webview or browser error page. Retry re-initiates
the full sequence: backend health poll → frontend load.

---

## Debugging / Individual Processes

When you need to run components separately (e.g. to debug startup):

```bash
# Backend only (port 8000)
bash scripts/dev_backend.sh

# Frontend only (port 5173, proxies /api to 8000)
cd frontend && npm run dev

# Shell only (requires backend + frontend already running on 8000/5173)
bash scripts/dev_desktop.sh
```

---

## Config

Shell runtime constants are at the top of `desktop/app/window.py`:

```python
BACKEND_HEALTH_URL  # reads FLASHPOINT_BACKEND_HEALTH_URL env var; fallback: localhost:8000
FRONTEND_URL        # reads FLASHPOINT_FRONTEND_URL env var; fallback: localhost:5173
HEALTH_POLL_INTERVAL_MS = 2_000
HEALTH_POLL_TIMEOUT_S   = 3
HEALTH_MAX_FAILURES     = 10
```

Launcher managed-port constants are at the top of `desktop/app/launcher.py`:

```python
MANAGED_BACKEND_PORT  = 8001
MANAGED_FRONTEND_PORT = 5178
```

---

## Pi Future-Readiness

### FLASHPOINT_MANAGED=1

Set this env var to skip subprocess management in the launcher and go straight to
the shell. The shell's health poller is the readiness gate. Use this when services
are managed externally (systemd, autostart).

Pi autostart entry (`~/.config/labwc/autostart`) can be as simple as:

```
FLASHPOINT_MANAGED=1 bash /path/to/repo/scripts/run.sh &
```

### Future milestone table

| Future milestone | What to add |
|---|---|
| Pi autostart | `~/.config/labwc/autostart` or systemd user service with `FLASHPOINT_MANAGED=1` |
| Backend service | `systemd` unit managing `uvicorn`; shell waits via health poll (already wired) |
| Portrait / touch | Window geometry tuning, touch-friendly Qt event handling |
| Frontend URL | Change `FLASHPOINT_FRONTEND_URL` → `http://localhost:8000` once FastAPI serves built frontend |
| Remove quit shortcut | Guard `Ctrl+Q` / `Command+Q` behind a `DEV_MODE` env var |
| Native surfaces | Replace overlay widget → richer native startup screen |

---

## Out of Scope (this milestone)

- Full Pi packaging or autostart
- Settings / preferences panel
- Production systemd service definitions
- Rewriting any React panels into Qt widgets
- Backend refactors
- Electron
