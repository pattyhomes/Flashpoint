"""
Flashpoint Runtime Launcher — orchestrated desktop startup.

TRANSITIONAL: This module starts backend and frontend as managed subprocesses for
local development. On Pi, the backend will be a systemd service and the frontend
will be served from the built artifact — set FLASHPOINT_MANAGED=1 to skip
subprocess management and go straight to launching the shell.

Startup sequence (unmanaged / dev mode):
  1. Preflight: verify ports 8001 and 5178 are free
  2. Check prereqs: .venv/bin/uvicorn, npm, .env
  3. Export FLASHPOINT_BACKEND_HEALTH_URL and FLASHPOINT_FRONTEND_URL so the shell
     picks up managed URLs before window.py is imported
  4. Start backend subprocess (uvicorn on 8001) in its own session
  5. Poll /api/v1/health until HTTP 200 or timeout
  6. Start frontend subprocess (npm run dev on 5178) in its own session,
     with VITE_PORT and VITE_BACKEND_PORT injected
  7. Poll HTTP GET 127.0.0.1:5178 until a response is received or timeout
  8. Call desktop.app.main.main() inline — blocks until the shell exits
     (Command+Q on macOS, Ctrl+Q on Windows/Linux)
  9. Finally: terminate frontend process group, then backend process group

Process groups: start_new_session=True puts each child in its own session so all
descendants (uvicorn reload workers, Node children) are captured on shutdown.
Shutdown uses os.killpg — not proc.terminate() — to reach the whole group.

Pi path (FLASHPOINT_MANAGED=1):
  Services are managed externally. The launcher sets env vars and launches the shell.
  The shell's existing health poller is the readiness gate.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from desktop.app import config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[launcher] {msg}", flush=True)


def _check_port_free(port: int) -> bool:
    """Return True if the port is not accepting connections (i.e. is free)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_http(url: str, timeout_s: int, proc: subprocess.Popen, name: str = "Service") -> None:
    """
    Poll `url` until any HTTP response is received or timeout.
    Checks that `proc` is still alive on each iteration.
    Raises SystemExit with a clear message on failure.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            sys.exit(f"[launcher] {name} process exited unexpectedly (rc={proc.returncode})")
        try:
            with urlopen(url, timeout=2) as _:
                return  # any response means the server is up
        except Exception:
            pass
        time.sleep(0.5)
    sys.exit(f"[launcher] {name} did not become ready within {timeout_s}s ({url})")


def _stop_process_group(proc: subprocess.Popen | None, name: str, timeout_s: int = 5) -> None:
    """
    Gracefully terminate a process group (SIGTERM → wait → SIGKILL).
    Uses os.killpg to reach all descendants (reload workers, Node children, etc.).
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return  # already gone

    _log(f"Stopping {name} (pgid={pgid})…")
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=timeout_s)
        _log(f"{name} stopped.")
    except subprocess.TimeoutExpired:
        _log(f"{name} did not exit within {timeout_s}s — killing process group.")
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        _log(f"{name} killed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent

    managed = config.MANAGED

    # Inject managed URLs into the environment so window.py picks them up
    # before it is imported by desktop.app.main.
    os.environ["FLASHPOINT_BACKEND_HEALTH_URL"] = config.MANAGED_BACKEND_HEALTH_URL
    os.environ["FLASHPOINT_FRONTEND_URL"] = config.MANAGED_FRONTEND_URL

    if managed:
        # TRANSITIONAL: Pi path — services managed externally (systemd, autostart).
        # Skip subprocess management; shell health poller is the readiness gate.
        _log("FLASHPOINT_MANAGED=1 — skipping subprocess management.")
        _launch_shell()
        return

    # ------------------------------------------------------------------
    # Preflight checks
    # ------------------------------------------------------------------

    for port in (config.MANAGED_BACKEND_PORT, config.MANAGED_FRONTEND_PORT):
        if not _check_port_free(port):
            sys.exit(
                f"[launcher] Port {port} is already in use. "
                f"Stop the existing process or use standalone scripts."
            )

    venv_uvicorn = repo_root / ".venv" / "bin" / "uvicorn"
    if not venv_uvicorn.exists():
        sys.exit(
            f"[launcher] .venv/bin/uvicorn not found. "
            f"Run: pip install -r backend/requirements.txt"
        )

    env_file = repo_root / ".env"
    if not env_file.exists():
        sys.exit(
            f"[launcher] .env not found. Run: cp .env.example .env"
        )

    # ------------------------------------------------------------------
    # Start managed processes
    # ------------------------------------------------------------------

    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None

    try:
        _log(f"Starting backend on port {config.MANAGED_BACKEND_PORT}…")
        backend_proc = subprocess.Popen(
            [
                str(venv_uvicorn),
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", str(config.MANAGED_BACKEND_PORT),
                "--reload",
            ],
            cwd=str(repo_root / "backend"),
            start_new_session=True,
        )

        _log("Waiting for backend to be ready…")
        _wait_for_http(config.MANAGED_BACKEND_HEALTH_URL, config.BACKEND_READY_TIMEOUT_S, backend_proc, name="Backend")
        _log("Backend ready.")

        _log(f"Starting frontend on port {config.MANAGED_FRONTEND_PORT}…")
        frontend_env = {
            **os.environ,
            "VITE_PORT": str(config.MANAGED_FRONTEND_PORT),
            "VITE_HOST": "127.0.0.1",          # bind explicitly so readiness check hits the right address
            "VITE_BACKEND_PORT": str(config.MANAGED_BACKEND_PORT),
        }
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(repo_root / "frontend"),
            env=frontend_env,
            start_new_session=True,
        )

        _log("Waiting for frontend to be ready…")
        _wait_for_http(config.MANAGED_FRONTEND_URL, config.FRONTEND_READY_TIMEOUT_S, frontend_proc, name="Frontend")
        _log("Frontend ready.")

        _launch_shell()

    except KeyboardInterrupt:
        _log("Interrupted.")
    finally:
        _stop_process_group(frontend_proc, "frontend")
        _stop_process_group(backend_proc, "backend")
        _log("Done.")


def _launch_shell() -> None:
    """Import and run the PySide6 shell inline (same process)."""
    # Import is deferred until here so the env vars set above are already in
    # place when window.py is loaded and its module-level constants are evaluated.
    from desktop.app.main import main as shell_main  # noqa: PLC0415
    shell_main()


if __name__ == "__main__":
    main()
