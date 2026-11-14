"""Meetings export controls use selected saved data and reject dirty editors."""

import os

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from test_meetings_page import select_meeting
from test_minutes_store import make_meeting_with_run, sample_content

from fahmm.minutes_store import MinutesStore
from fahmm.models import ModelManager
from fahmm.storage import MeetingStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_export_controls_select_saved_content_and_block_dirty_editors(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    version_id = MinutesStore(store).save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    page.show()
    select_meeting(page, meeting_id)
    transcript_path = tmp_path / "transcript.txt"
    minutes_path = tmp_path / "minutes.md"
    destinations = iter([(str(transcript_path), ""), (str(minutes_path), "")])
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: next(destinations))
    notices = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[2]))
    assert page.export_transcript_button.isEnabled()
    assert page.minutes_panel.export_minutes_button.isEnabled()
    page.export_transcript_button.click()
    page.minutes_panel.export_minutes_button.click()
    assert transcript_path.read_text(encoding="utf-8").startswith("[00:00:00.0")
    assert "Đã thống nhất thử nghiệm." in minutes_path.read_text(encoding="utf-8")
    assert page.minutes_panel.version_box.currentData() == version_id

    page.segment_table.item(0, 1).setText("Not saved")
    page.export_transcript_button.click()
    assert "Save transcript edits" in notices[-1]
    assert "Not saved" not in transcript_path.read_text(encoding="utf-8")
    page.minutes_panel.content_edit.appendPlainText("Not saved")
    page.minutes_panel.export_minutes_button.click()
    assert "Save minutes edits" in notices[-1]
    assert "Not saved" not in minutes_path.read_text(encoding="utf-8")
    page.close()


def test_export_buttons_unavailable_without_saved_run_or_minutes(tmp_path):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store = MeetingStore(tmp_path / "meetings")
    meeting_id = store.create({})
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    page.show()
    select_meeting(page, meeting_id)
    assert not page.export_transcript_button.isEnabled()
    assert not page.minutes_panel.export_minutes_button.isEnabled()
    page.close()


def test_copy_markdown_is_plain_text_and_blocks_unsaved_minutes(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    version_id = MinutesStore(store).save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    page.show()
    select_meeting(page, meeting_id)
    clipboard = QApplication.clipboard()
    clipboard.clear()
    panel = page.minutes_panel
    assert panel.version_box.currentData() == version_id
    assert clipboard.text() == ""
    panel.copy_markdown_button.click()
    expected = panel.exporter.minutes_markdown(meeting_id, version_id)
    assert clipboard.text() == expected
    assert clipboard.mimeData().formats() == ["text/plain"]
    notices = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[2]))
    panel.content_edit.appendPlainText("Unsaved addition")
    panel.copy_markdown_button.click()
    assert "Save minutes edits" in notices[-1]
    assert clipboard.text() == expected
    page.close()
