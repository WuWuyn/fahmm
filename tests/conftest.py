"""Keep the legacy Qt application alive across UI test modules on Windows."""

from __future__ import annotations

import os
import sys

_qt_application = None


def pytest_sessionstart() -> None:
    if sys.platform != "win32":
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return

    global _qt_application
    _qt_application = QApplication.instance() or QApplication([])


def pytest_sessionfinish() -> None:
    if _qt_application is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in _qt_application.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _qt_application.processEvents()
