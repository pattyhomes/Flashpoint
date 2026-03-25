"""
Flashpoint Desktop Shell — main window.

TRANSITIONAL ARCHITECTURE: This shell embeds the React/Vite frontend via
QWebEngineView. The backend (FastAPI) and frontend (React/MapLibre) are
unchanged. The shell's job is to:

  1. Show a native loading/connecting state immediately on launch
  2. Poll the backend health endpoint until the backend is ready
  3. Load the operational web UI inside the shell once the backend responds
  4. Show a native unavailable + retry state if the backend does not respond
  5. Stay out of the way during normal operation

Future work: selected surfaces (status bar, startup screen) will move to
native Qt widgets. The map and feed will remain web-rendered.

See desktop/README.md for the full transitional-architecture rationale.
"""
import os
from urllib.request import urlopen

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Runtime config
#
# URLs are read from environment variables so the launcher can inject managed
# ports (8001/5178) for the orchestrated path without changing this file.
# Standalone dev (dev_desktop.sh) sets no env vars → falls back to defaults.
#
# FRONTEND_URL in dev:  Vite dev server proxies /api → backend.
# FRONTEND_URL on Pi:   Will point to the backend serving the built frontend
#                       once static-file serving is added to FastAPI
#                       (Milestone B/C work).
# ---------------------------------------------------------------------------

BACKEND_HEALTH_URL = os.environ.get(
    "FLASHPOINT_BACKEND_HEALTH_URL",
    "http://localhost:8000/api/v1/health",   # standalone dev default
)
FRONTEND_URL = os.environ.get(
    "FLASHPOINT_FRONTEND_URL",
    "http://localhost:5173",                 # standalone dev default
)
HEALTH_POLL_INTERVAL_MS = 2_000   # ms between poll attempts
HEALTH_POLL_TIMEOUT_S   = 3       # per-request HTTP timeout
HEALTH_MAX_FAILURES     = 10      # give up after this many consecutive failures


# ---------------------------------------------------------------------------
# Background health poller
# ---------------------------------------------------------------------------

class _HealthPoller(QThread):
    """
    Polls BACKEND_HEALTH_URL in a background thread.

    Emits `ready` on first HTTP 200 response, then exits.
    Emits `unavailable` after HEALTH_MAX_FAILURES consecutive failures, then exits.
    Call stop() to cancel early (e.g. on retry or window close).
    """

    ready       = Signal()
    unavailable = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._stop_flag = False

    def stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        failures = 0
        while not self._stop_flag:
            try:
                with urlopen(BACKEND_HEALTH_URL, timeout=HEALTH_POLL_TIMEOUT_S) as resp:
                    if resp.status == 200:
                        self.ready.emit()
                        return
                    else:
                        failures += 1
            except Exception:
                failures += 1

            if failures >= HEALTH_MAX_FAILURES:
                self.unavailable.emit()
                return

            # Sleep in 100ms steps so the stop flag is checked frequently
            for _ in range(HEALTH_POLL_INTERVAL_MS // 100):
                if self._stop_flag:
                    return
                self.msleep(100)


# ---------------------------------------------------------------------------
# Native overlay widget
# ---------------------------------------------------------------------------

_OVERLAY_CSS = """
QWidget#overlay {
    background: #080a0e;
}
QLabel#app-name {
    font-family: 'Courier New', 'Courier', monospace;
    font-size: 13px;
    letter-spacing: 6px;
    color: #4a9eff;
    font-weight: 600;
}
QLabel#status {
    font-family: 'Courier New', 'Courier', monospace;
    font-size: 11px;
    letter-spacing: 2px;
    color: #4a5568;
}
QPushButton#retry {
    font-family: 'Courier New', 'Courier', monospace;
    font-size: 11px;
    letter-spacing: 2px;
    color: #9aa0b0;
    background: transparent;
    border: 1px solid #2a2f3a;
    border-radius: 4px;
    padding: 6px 20px;
    min-width: 80px;
}
QPushButton#retry:hover {
    color: #d0d4de;
    border-color: #4a5568;
}
"""


class _OverlayWidget(QWidget):
    """
    Native dark overlay shown during connecting and unavailable states.
    Matches the app's dark tactical aesthetic without loading the web UI.
    """

    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("overlay")
        self.setStyleSheet(_OVERLAY_CSS)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        name_label = QLabel("FLASHPOINT")
        name_label.setObjectName("app-name")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status_label = QLabel("Connecting…")
        self._status_label.setObjectName("status")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setObjectName("retry")
        self._retry_btn.setVisible(False)
        self._retry_btn.clicked.connect(self.retry_requested)

        layout.addWidget(name_label)
        layout.addWidget(self._status_label)
        layout.addWidget(self._retry_btn)

    def set_connecting(self) -> None:
        self._status_label.setText("Connecting…")
        self._retry_btn.setVisible(False)

    def set_unavailable(self, message: str = "Backend not responding") -> None:
        self._status_label.setText(message)
        self._retry_btn.setVisible(True)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """
    Flashpoint shell window.

    State machine:

        CONNECTING (initial)
            ─ backend ready    ──► load webview → LOADING_WEBVIEW
            ─ unavailable      ──► show overlay → UNAVAILABLE

        LOADING_WEBVIEW
            ─ loadFinished(ok)  ──► show webview → READY
            ─ loadFinished(err) ──► show overlay → UNAVAILABLE

        UNAVAILABLE
            ─ retry_requested  ──► stop poller, new poller → CONNECTING

        READY  ← normal operation; shell stays out of the way
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Flashpoint")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        )

        # Stacked widget: index 0 = native overlay, index 1 = web view
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Page 0 — native overlay (connecting / unavailable)
        self._overlay = _OverlayWidget()
        self._overlay.retry_requested.connect(self._start_connecting)
        self._stack.addWidget(self._overlay)

        # Page 1 — embedded web UI
        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._webview.loadFinished.connect(self._on_load_finished)
        self._stack.addWidget(self._webview)

        # Dev convenience: Ctrl+Q exits.
        # TRANSITIONAL: remove or guard behind a dev flag for Pi production.
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(QApplication.quit)

        self._poller: _HealthPoller | None = None

        # Boot into connecting state
        self._start_connecting()

    # ── State transitions ──────────────────────────────────────────────────

    def _start_connecting(self) -> None:
        """Enter CONNECTING: show overlay and launch a fresh health poll."""
        self._overlay.set_connecting()
        self._stack.setCurrentIndex(0)
        self._stop_poller()
        self._poller = _HealthPoller()
        self._poller.ready.connect(self._on_backend_ready)
        self._poller.unavailable.connect(self._on_backend_unavailable)
        self._poller.start()

    def _on_backend_ready(self) -> None:
        """Backend health passed → start loading the web UI."""
        # Keep the overlay visible while the webview loads (avoids flash of blank)
        self._overlay.set_connecting()
        self._webview.setUrl(QUrl(FRONTEND_URL))

    def _on_load_finished(self, ok: bool) -> None:
        """Webview reported load complete."""
        if ok:
            self._stack.setCurrentIndex(1)  # Hand off to the web UI
        else:
            self._overlay.set_unavailable("Could not load the frontend")
            self._stack.setCurrentIndex(0)

    def _on_backend_unavailable(self) -> None:
        """Health poller exhausted its retry budget."""
        self._overlay.set_unavailable("Backend not responding")
        self._stack.setCurrentIndex(0)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def _stop_poller(self) -> None:
        if self._poller is not None:
            self._poller.stop()
            self._poller.quit()
            self._poller.wait(2_000)
            self._poller = None

    def closeEvent(self, event) -> None:
        self._stop_poller()
        super().closeEvent(event)
