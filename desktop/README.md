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
└── QWebEngineView ← React/Vite frontend (localhost:5173 in dev)
                       └── /api/* proxied to FastAPI backend (localhost:8000)
```

---

## Dev Setup (Mac)

**Prerequisites:** Python 3.11+, Node.js 18+, existing repo venv at `.venv/`

### 1. Install PySide6

```bash
# From the repo root
source .venv/bin/activate
pip install -r desktop/requirements.txt
```

PySide6 is ~400MB. Install once; it sits in `.venv/`.

### 2. Verify the install

```bash
.venv/bin/python -c "
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
print('PySide6 OK')
"
```

### 3. Run (3 terminals)

```bash
# Terminal 1 — backend
bash scripts/dev_backend.sh

# Terminal 2 — frontend dev server
cd frontend && npm run dev

# Terminal 3 — desktop shell
bash scripts/dev_desktop.sh
```

The shell will show "Connecting…" until the backend responds to
`GET /api/v1/health`, then load the React UI inside the window.

**Quit:** `Ctrl+Q`

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

## Config

Runtime constants are at the top of `desktop/app/window.py`:

```python
BACKEND_HEALTH_URL      = "http://localhost:8000/api/v1/health"
FRONTEND_URL            = "http://localhost:5173"   # Vite dev; change for Pi
HEALTH_POLL_INTERVAL_MS = 2_000
HEALTH_POLL_TIMEOUT_S   = 3
HEALTH_MAX_FAILURES     = 10
```

For Pi production, `FRONTEND_URL` will point to the backend serving the built
frontend (requires static-file serving to be added to FastAPI — Milestone B/C work).

---

## Pi Future-Readiness

This scaffold is structured for later work:

| Future milestone | What to add |
|---|---|
| Pi autostart | `~/.config/labwc/autostart` or systemd user service launching `dev_desktop.sh` |
| Backend service | `systemd` unit managing `uvicorn`; shell waits for it via health poll (already wired) |
| Portrait / touch | Window geometry tuning, touch-friendly Qt event handling |
| Frontend URL | Change `FRONTEND_URL` → `http://localhost:8000` once FastAPI serves built frontend |
| Remove Ctrl+Q | Guard the shortcut behind a `DEV_MODE` env var |
| Native surfaces | Replace overlay widget → richer native startup screen |

---

## Out of Scope (this milestone)

- Full Pi packaging or autostart
- Settings / preferences panel
- Production systemd service definitions
- Rewriting any React panels into Qt widgets
- Backend refactors
- Electron
