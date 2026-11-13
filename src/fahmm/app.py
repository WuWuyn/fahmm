"""Application entry point. Importing this module has no capture side effects."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from fahmm.audio import SoundCardCapture
from fahmm.controller import SessionController
from fahmm.storage import MeetingStore
from fahmm.ui import RecorderWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = RecorderWindow(SessionController(SoundCardCapture(), MeetingStore()))
    window.show()
    if "--smoke" in sys.argv:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
