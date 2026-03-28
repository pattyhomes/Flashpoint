"""
Qt compatibility layer for the Flashpoint desktop shell.

Priority order:
  1. PyQt6  — Raspberry Pi OS Bookworm (system package, supports 16KB pages on RPi 5)
  2. PySide6 — Mac / pip-installed path
  3. PyQt5  — legacy fallback (does NOT work on RPi 5 — 16KB page crash in Chromium 87)

Why PyQt6 on Pi:
  The RPi 5 kernel uses 16KB memory pages. Qt5 WebEngine embeds Chromium 87, whose
  PartitionAlloc hardcodes 4KB page assumptions and crashes (FATAL page_allocator
  mmap EINVAL) on boot. Qt6 WebEngine 6.4.2 from Debian Bookworm supports 16KB pages.
  pip-installed PySide6 also fails on Bookworm — it links against libwebp.so.6 but
  Bookworm provides libwebp.so.7.

Differences handled here:
  1. Signal  — PySide6: Signal; PyQt6/PyQt5: pyqtSignal (aliased to Signal)
  2. QShortcut location — PySide6/PyQt6: QtGui; PyQt5: QtWidgets
  3. Enum scoping — window.py uses fully-qualified enum paths
     (Qt.AlignmentFlag.AlignCenter, Qt.WindowType.*, Qt.ContextMenuPolicy.*)
     which work in PySide6, PyQt6, and PyQt5 5.15+.

Pi setup:
  sudo apt install python3-pyqt6 python3-pyqt6.qtwebengine
  python3 -m venv --system-site-packages .venv
  pip install -e .  # do NOT install desktop/requirements.txt on Pi

Mac setup:
  pip install -r desktop/requirements.txt  (PySide6)
"""

try:
    from PyQt6.QtCore import Qt, QThread, QUrl                        # noqa: F401
    from PyQt6.QtCore import pyqtSignal as Signal                     # noqa: F401
    from PyQt6.QtGui import QKeySequence, QShortcut                   # noqa: F401
    from PyQt6.QtWebEngineWidgets import QWebEngineView               # noqa: F401
    from PyQt6.QtWidgets import (                                     # noqa: F401
        QApplication,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    try:
        from PySide6.QtCore import Qt, QThread, QUrl, Signal          # noqa: F401
        from PySide6.QtGui import QKeySequence, QShortcut             # noqa: F401
        from PySide6.QtWebEngineWidgets import QWebEngineView         # noqa: F401
        from PySide6.QtWidgets import (                               # noqa: F401
            QApplication,
            QLabel,
            QMainWindow,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        from PyQt5.QtCore import Qt, QThread, QUrl                    # noqa: F401
        from PyQt5.QtCore import pyqtSignal as Signal                 # noqa: F401
        from PyQt5.QtGui import QKeySequence                          # noqa: F401
        from PyQt5.QtWidgets import QShortcut                         # noqa: F401  Qt5: moved to QtWidgets
        from PyQt5.QtWebEngineWidgets import QWebEngineView           # noqa: F401
        from PyQt5.QtWidgets import (                                 # noqa: F401
            QApplication,
            QLabel,
            QMainWindow,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )
