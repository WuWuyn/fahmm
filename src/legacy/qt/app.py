"""Application entry point. Importing this module has no capture side effects."""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from fahmm.audio import SoundCardCapture
from fahmm.controller import SessionController
from fahmm.single_instance import AlreadyRunningError, SingleInstanceLock
from fahmm.storage import MeetingStore
from legacy.qt.ui import RecorderWindow


def main() -> int:
    store = MeetingStore()
    instance = SingleInstanceLock(store.root.parent)
    try:
        instance.acquire()
    except AlreadyRunningError as exc:
        if "--smoke" in sys.argv:
            return 2
        app = QApplication(sys.argv)
        QMessageBox.information(app.activeWindow(), "fahmm is already open", str(exc))
        return 2
    try:
        return _run_app(store)
    finally:
        instance.release()


def _run_app(store: MeetingStore) -> int:
    app = QApplication(sys.argv)
    window = RecorderWindow(SessionController(SoundCardCapture(), store))
    window.show()
    if "--smoke" in sys.argv:
        QTimer.singleShot(500, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
