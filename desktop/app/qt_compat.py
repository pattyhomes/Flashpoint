"""
Qt compatibility layer for the Flashpoint desktop shell.

Tries PySide6 first (Mac / pip-installed path).
Falls back to PyQt5 (Raspberry Pi OS / system-package path).

On Raspberry Pi OS Bookworm, pip-installed PySide6 links against
`libwebp.so.6` but Bookworm provides `libwebp.so.7`, causing an
import failure. The solution is to use the system-native PyQt5
package on Pi and import through this module everywhere.

Differences handled here:
  1. Signal  — PySide6: Signal; PyQt5: pyqtSignal (aliased to Signal)
  2. QShortcut location — PySide6: QtGui; PyQt5: QtWidgets
  3. Enum scoping — handled at call sites (short-form enums used
     throughout window.py, which work in both PySide6 and PyQt5)

Pi setup:
  sudo apt install python3-pyqt5 python3-pyqt5.qtwebengine
  python3 -m venv --system-site-packages .venv
  pip install -e .  # do NOT install desktop/requirements.txt on Pi

Mac setup:
  pip install -r desktop/requirements.txt  (PySide6)
"""

try:
    from PySide6.QtCore import Qt, QThread, QUrl, Signal              # noqa: F401
    from PySide6.QtGui import QKeySequence, QShortcut                 # noqa: F401
    from PySide6.QtWebEngineWidgets import QWebEngineView             # noqa: F401
    from PySide6.QtWidgets import (                                   # noqa: F401
        QApplication,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    from PyQt5.QtCore import Qt, QThread, QUrl                        # noqa: F401
    from PyQt5.QtCore import pyqtSignal as Signal                     # noqa: F401
    from PyQt5.QtGui import QKeySequence                              # noqa: F401
    from PyQt5.QtWidgets import QShortcut                             # noqa: F401  Qt5: moved to QtWidgets
    from PyQt5.QtWebEngineWidgets import QWebEngineView               # noqa: F401
    from PyQt5.QtWidgets import (                                     # noqa: F401
        QApplication,
        QLabel,
        QMainWindow,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
