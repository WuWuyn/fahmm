import os
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_controller import FakeCapture

from fahmm.controller import SessionController, State
from fahmm.storage import MeetingStore
from fahmm.ui import RecorderWindow

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def _app():
    return QApplication.instance() or QApplication([])


def _wait_state(controller, state):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        QTest.qWait(30)
        if controller.snapshot().state == state:
            return
    raise AssertionError(controller.snapshot())


def test_ui_controls_and_timer_remain_responsive(tmp_path):
    _app()
    controller = SessionController(FakeCapture(), MeetingStore(tmp_path))
    window = RecorderWindow(controller)
    window.show()
    window.activateWindow()
    window.setFocus()
    QTest.qWait(50)
    assert window.system_box.count() == 1
    assert window.microphone_box.count() == 1
    assert window.status_label.text() == "Ready to record"
    assert window.record_button.text() == "Record"
    assert window.stop_button.text() == "Stop and save"
    assert window.record_button.isEnabled()
    QTest.keyClick(window, Qt.Key_R, Qt.ControlModifier)
    _wait_state(controller, State.RECORDING)
    reached = []
    QTimer.singleShot(20, lambda: reached.append(True))
    QTest.qWait(80)
    assert reached
    window._tick()
    assert window.pause_button.isEnabled()
    QTest.keyClick(window, Qt.Key_Space)
    assert controller.snapshot().state == State.PAUSED
    assert window.pause_button.text() == "Resume"
    QTest.keyClick(window, Qt.Key_Space)
    assert controller.snapshot().state == State.RECORDING
    QTest.keyClick(window, Qt.Key_S, Qt.ControlModifier)
    _wait_state(controller, State.COMPLETED)
    window._tick()
    assert "recording.wav" in window.result_label.text()
    window.close()


def test_ui_offers_recovery_and_displays_result(tmp_path):
    _app()
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(meeting, "system", 0, np.ones(1000))
    controller = SessionController(FakeCapture(), store)
    window = RecorderWindow(controller)
    window.show()
    assert window.recovery_list.count() == 1
    assert window.recover_button.text() == "Recover selected recording"
    window.recovery_list.setCurrentRow(0)
    window._tick()
    assert window.recover_button.isEnabled()
    window.recover_button.click()
    _wait_state(controller, State.COMPLETED)
    window._tick()
    assert "recording.wav" in window.result_label.text()
    assert window.recovery_list.count() == 0
    window.close()
