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

All desktop runtime constants live in **`desktop/app/config.py`** — the single source of truth for both the launcher and the shell. Neither `launcher.py` nor `window.py` define their own constants; they import from `config`.

```python
# Standalone URL defaults (fallbacks when no env vars are set)
STANDALONE_BACKEND_HEALTH_URL = "http://localhost:8000/api/v1/health"
STANDALONE_FRONTEND_URL       = "http://localhost:5173"

# Managed ports (orchestrated path)
MANAGED_BACKEND_PORT  = 8001
MANAGED_FRONTEND_PORT = 5178

# Launcher readiness timeouts
BACKEND_READY_TIMEOUT_S  = 30
FRONTEND_READY_TIMEOUT_S = 30

# Shell health poller
HEALTH_POLL_INTERVAL_MS = 2_000
HEALTH_POLL_TIMEOUT_S   = 3
HEALTH_MAX_FAILURES     = 10
```

**URL exception:** `BACKEND_HEALTH_URL` and `FRONTEND_URL` (as runtime-resolved values) are still read in `window.py` at import time via `os.environ.get(...)`, because the launcher injects those env vars *after* `config.py` is first imported. The `STANDALONE_*` strings in `config.py` serve as the fallback values.

### Pi seam env vars

| Env var | Default | What it does |
|---|---|---|
| `FLASHPOINT_FULLSCREEN` | `0` | `1` → `showFullScreen()` for Pi production |
| `FLASHPOINT_DEV_QUIT` | `1` | `0` → custom `QShortcut` (Ctrl+Q / Command+Q) not registered |
| `FLASHPOINT_MANAGED` | `0` | `1` → launcher skips subprocess management (services external) |
| `FLASHPOINT_PORTRAIT` | `0` | **Future use only** — not yet wired to any geometry or orientation behavior |

All seam vars are documented in `.env.example` with the `FLASHPOINT_*` prefix.

---

## Pi Runtime

Pi autostart and service scaffolding is in `deploy/pi/`. See **`deploy/pi/README.md`**
for the full setup guide, boot flow, and known gaps.

**Quick summary:**
- Backend runs as a systemd user service (`flashpoint-backend.service`)
- Shell autostarts via XDG autostart (`flashpoint.desktop` → `scripts/pi_start.sh`)
- `scripts/pi_start.sh` sets `FLASHPOINT_MANAGED=1`, `FLASHPOINT_FULLSCREEN=1`,
  `FLASHPOINT_DEV_QUIT=0`, `FLASHPOINT_BACKEND_HEALTH_URL=http://127.0.0.1:8000/api/v1/health`,
  and `FLASHPOINT_FRONTEND_URL=http://127.0.0.1:8000`
- Install with: `bash deploy/pi/install.sh`

**Frontend delivery:** The backend serves `frontend/dist/` via FastAPI `StaticFiles` at `/`.
`pi_start.sh` points the shell at `http://127.0.0.1:8000` — no separate Vite server needed
on Pi. The `frontend/dist/` directory must be built before the backend starts (one-time step).
See `deploy/pi/README.md` Prerequisites for build instructions.

### Remaining milestones

| Milestone | Status |
|---|---|
| Frontend delivery for Pi | Implemented, Mac-validated — hardware validation pending |
| Hardware validation | Boot → READY flow not yet tested on Pi hardware |
| Portrait / touch | Wire `FLASHPOINT_PORTRAIT=1` to window geometry; touch-friendly Qt event handling |
| Native surfaces | Replace overlay widget → richer native startup screen (Milestone C) |

---

## Out of Scope (this milestone)

- Full Pi packaging or autostart
- Settings / preferences panel
- Production systemd service definitions
- Rewriting any React panels into Qt widgets
- Backend refactors
- Electron
