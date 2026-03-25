"""
Flashpoint Desktop Runtime Configuration

Single source of truth for all desktop shell and launcher constants.
Both launcher.py and window.py import from here.

Three tiers:
  STANDALONE — direct-script defaults (dev_backend.sh, dev_desktop.sh, npm run dev)
  MANAGED    — orchestrated path (scripts/run.sh via launcher.py)
  PI_SEAMS   — env-var flags for Pi deployment, toggled without code edits

URL constants BACKEND_HEALTH_URL and FRONTEND_URL are NOT defined here.
launcher.py injects their managed values as env vars (FLASHPOINT_BACKEND_HEALTH_URL /
FLASHPOINT_FRONTEND_URL) after this module is first imported. window.py reads those
env vars at its own (deferred) import time and uses the STANDALONE_* strings below
as fallbacks. Defining them here would capture standalone defaults at launcher import
time and make them permanently stale by the time window.py runs.
"""
import os

# ---------------------------------------------------------------------------
# Standalone URL defaults
# Used as env-var fallbacks in window.py for the direct-script path.
# ---------------------------------------------------------------------------

STANDALONE_BACKEND_HEALTH_URL = "http://localhost:8000/api/v1/health"
STANDALONE_FRONTEND_URL       = "http://localhost:5173"

# ---------------------------------------------------------------------------
# Managed ports (orchestrated path — scripts/run.sh via launcher.py)
#
# Launcher starts backend and frontend on these dedicated ports so they don't
# collide with standalone dev sessions. Standalone paths keep 8000 / 5173.
# ---------------------------------------------------------------------------

MANAGED_BACKEND_PORT: int  = 8001
MANAGED_FRONTEND_PORT: int = 5178

# Derived managed URLs (used by launcher to poll readiness and inject env vars)
MANAGED_BACKEND_HEALTH_URL = f"http://127.0.0.1:{MANAGED_BACKEND_PORT}/api/v1/health"
MANAGED_FRONTEND_URL       = f"http://127.0.0.1:{MANAGED_FRONTEND_PORT}"

# ---------------------------------------------------------------------------
# Launcher readiness timeouts
# How long to wait for each service to respond before aborting startup.
# ---------------------------------------------------------------------------

BACKEND_READY_TIMEOUT_S: int  = 30
FRONTEND_READY_TIMEOUT_S: int = 30

# ---------------------------------------------------------------------------
# Shell health poller
# Controls how aggressively the shell polls the backend after launch.
# ---------------------------------------------------------------------------

HEALTH_POLL_INTERVAL_MS: int = 2_000   # ms between poll attempts
HEALTH_POLL_TIMEOUT_S: int   = 3       # per-request HTTP timeout (seconds)
HEALTH_MAX_FAILURES: int     = 10      # consecutive failures before UNAVAILABLE state

# ---------------------------------------------------------------------------
# PI_SEAM: fullscreen window
#
#   FLASHPOINT_FULLSCREEN=1 → showFullScreen() (Pi production)
#   default "0"             → window.show(), windowed (current Mac dev behavior)
# ---------------------------------------------------------------------------

FULLSCREEN: bool = os.environ.get("FLASHPOINT_FULLSCREEN", "0") != "0"

# ---------------------------------------------------------------------------
# PI_SEAM: custom dev quit shortcut (QShortcut "Ctrl+Q", maps to Command+Q on macOS)
#
#   FLASHPOINT_DEV_QUIT=0 → custom QShortcut not registered (Pi production)
#   default "1"           → custom QShortcut active (current dev behavior)
#
#   NOTE: this flag only gates the explicit QShortcut registration in window.py.
#   Platform-level quit paths (e.g. macOS application menu) are not affected.
# ---------------------------------------------------------------------------

DEV_QUIT_ENABLED: bool = os.environ.get("FLASHPOINT_DEV_QUIT", "1") != "0"

# ---------------------------------------------------------------------------
# PI_SEAM: managed mode
#
#   FLASHPOINT_MANAGED=1 → launcher skips subprocess management; services are
#                          managed externally (systemd, autostart)
#   default "0"          → launcher manages backend + frontend subprocesses
# ---------------------------------------------------------------------------

MANAGED: bool = os.environ.get("FLASHPOINT_MANAGED", "0") == "1"

# ---------------------------------------------------------------------------
# PI_SEAM: portrait display mode
#
#   FUTURE USE ONLY — this constant is defined as a named seam but is NOT yet
#   wired to any window geometry, orientation, or display behavior. Setting it
#   to "1" currently has no runtime effect. Implementation is deferred to
#   Milestone B (Pi Runtime Integration).
#
#   FLASHPOINT_PORTRAIT=1 → (future) portrait 720×1280 for Pi Touch Display 2
#   default "0"           → no portrait adjustment
# ---------------------------------------------------------------------------

PORTRAIT_MODE: bool = os.environ.get("FLASHPOINT_PORTRAIT", "0") != "0"
