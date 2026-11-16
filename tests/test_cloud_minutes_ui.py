import os
import threading

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit
from test_cloud_minutes import make_cloud_service
from test_controller import FakeCapture
from test_meetings_page import select_meeting, wait_until

from fahmm.controller import SessionController
from fahmm.models import ModelManager
from fahmm.provider_transport import ProviderError
from legacy.qt.meetings_page import MeetingsPage
from legacy.qt.ui import RecorderWindow

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_cloud_ui_requires_mode_review_and_each_confirmation(tmp_path):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    service, meeting_id, _, _, _ = make_cloud_service(tmp_path)
    service.meetings.set_privacy_mode(meeting_id, "restricted")
    calls = []
    service._transport = lambda snapshot, _key: calls.append(snapshot.digest) or "# Biên bản"
    page = MeetingsPage(
        service.meetings,
        ModelManager(tmp_path / "models"),
        profiles=service.profiles,
        cloud_service=service,
    )
    page.show()
    select_meeting(page, meeting_id)
    panel = page.minutes_panel
    page.segment_table.setCurrentCell(0, 1)
    panel.review_checkbox.setChecked(True)
    assert not panel.cloud_button.isEnabled()
    panel.mode_box.setCurrentIndex(panel.mode_box.findData("cloud_permitted"))
    assert panel.cloud_button.isEnabled()

    preview_bodies = []

    def cancel_dialog():
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        assert any("example.org" in label.text() for label in dialog.findChildren(QLabel))
        preview_bodies.append([edit.toPlainText() for edit in dialog.findChildren(QPlainTextEdit)])
        dialog.reject()

    QTimer.singleShot(0, cancel_dialog)
    panel.cloud_button.click()
    assert calls == []
    assert panel.version_box.count() == 0
    assert any("Reviewed corrected text" in body for body in preview_bodies[0])
    assert all("Unselected secret" not in body for body in preview_bodies[0])

    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    panel.cloud_button.click()
    wait_until(lambda: panel.version_box.count() == 1 and not panel._busy)
    assert len(calls) == 1
    assert "Unverified" in panel.review_label.text()

    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    panel.retry_button.click()
    wait_until(lambda: panel.version_box.count() == 2 and not panel._busy)
    assert len(calls) == 2
    page.close()
    QTest.qWait(20)


def test_provider_wait_keeps_navigation_responsive_and_errors_hide_key(tmp_path):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    service, meeting_id, _, _, _ = make_cloud_service(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def slow_transport(*_args):
        entered.set()
        release.wait(5)
        return "# Biên bản"

    service._transport = slow_transport
    window = RecorderWindow(
        SessionController(FakeCapture(), service.meetings),
        ModelManager(tmp_path / "models"),
        service.profiles,
        service,
    )
    window.show()
    window.switch_to("Meetings")
    page = window.meetings_page
    select_meeting(page, meeting_id)
    panel = page.minutes_panel
    page.segment_table.setCurrentCell(0, 1)
    panel.review_checkbox.setChecked(True)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    panel.cloud_button.click()
    wait_until(entered.is_set)
    fired = []
    QTimer.singleShot(40, lambda: fired.append(True))
    window.switch_to("Settings")
    QTest.qWait(80)
    assert fired and window.nav_buttons["Settings"].isChecked()
    window.switch_to("Meetings")
    assert window.nav_buttons["Meetings"].isChecked()
    release.set()
    wait_until(lambda: panel.version_box.count() == 1 and not panel._busy)
    assert panel.minutes.active_version(meeting_id)["manifest"]["review_state"] == "unverified"

    def fail_transport(*_args):
        raise ProviderError("network", "Could not reach the provider; retry")

    service._transport = fail_transport
    page.segment_table.setCurrentCell(0, 1)
    panel.review_checkbox.setChecked(True)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().accept())
    panel.cloud_button.click()
    wait_until(lambda: "Provider request failed" in panel.status_label.text())
    assert "test-secret-key" not in panel.status_label.text()
    assert panel.retry_button.isEnabled()
    window.close()
