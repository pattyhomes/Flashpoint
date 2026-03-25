#!/usr/bin/env python3
"""
Flashpoint Desktop Shell — entry point.

TRANSITIONAL ARCHITECTURE: PySide6 shell wrapping the React/Vite frontend
embedded via QWebEngineView. The FastAPI backend and React frontend are
unchanged; the shell owns fullscreen lifecycle, loading state, and
backend-unavailable/retry states.

Run from the repo root:
    .venv/bin/python -m desktop.app.main
Or via the convenience script:
    bash scripts/dev_desktop.sh

See desktop/README.md for full context and Pi future-readiness notes.
"""
import sys

from PySide6.QtWidgets import QApplication

from desktop.app.window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Flashpoint")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
