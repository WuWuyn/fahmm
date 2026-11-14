"""Meeting deletion requires a deliberate, scoped UI confirmation."""

import os

from PySide6.QtWidgets import QApplication, QMessageBox
from test_meetings_page import select_meeting

from fahmm import meeting_deletion
from fahmm.models import ModelManager
from fahmm.storage import MeetingStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_delete_confirmation_cancel_and_success(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store = MeetingStore(tmp_path / "meetings")
    selected = store.create({})
    other = store.create({})
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    page.show()
    select_meeting(page, selected)
    prompts = []
    stops = []
    monkeypatch.setattr(page.player, "stop", lambda: stops.append(True))

    def cancel(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", cancel)
    page.delete_button.click()
    assert store.metadata(selected)["id"] == selected
    assert stops == []
    assert "Untitled meeting" in prompts[-1]
    assert "system backups remain" in prompts[-1]
    assert "not secure erasure" in prompts[-1]

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_button.click()
    assert stops == [True]
    assert not store._meeting_dir(selected).exists()
    assert store.metadata(other)["id"] == other
    assert page.meeting_list.count() == 1
    assert page.status_label.text() == "Meeting data deleted locally"
    page.close()


def test_active_work_refusal_and_retry_cleanup(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store = MeetingStore(tmp_path / "meetings")
    selected = store.create({})
    other = store.create({})
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    select_meeting(page, selected)
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    store.begin_activity(selected, "asr")
    page.delete_button.click()
    assert store._meeting_dir(selected).exists()
    assert warnings and "active" in warnings[-1].lower()
    store.end_activity(selected, "asr")

    remove = meeting_deletion._remove_tree
    failed = False

    def fail_once(path):
        nonlocal failed
        if path.name == f".deleting-{selected}" and not failed:
            failed = True
            raise PermissionError("locked test file")
        return remove(path)

    monkeypatch.setattr(meeting_deletion, "_remove_tree", fail_once)
    page.delete_button.click()
    assert page.pending_deletions.count() == 1
    assert page.meeting_list.count() == 2  # The list is not refreshed on failure.
    page.pending_deletions.setCurrentRow(0)
    assert page.retry_cleanup_button.isEnabled()
    page.retry_cleanup_button.click()
    assert page.pending_deletions.count() == 0
    assert not store._meeting_dir(selected).exists()
    assert store.metadata(other)["id"] == other
    page.close()


def test_orphan_import_cleanup_requires_confirmation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store = MeetingStore(tmp_path / "meetings")
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    orphan_id = "a" * 32
    stage = store.root / f".import-{orphan_id}"
    stage.mkdir(parents=True)
    (stage / "partial.wav").write_bytes(b"partial")
    page._refresh_cleanup()
    assert page.orphan_imports.count() == 1
    page.orphan_imports.setCurrentRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    page.clean_import_button.click()
    assert stage.exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.clean_import_button.click()
    assert not stage.exists()
    assert page.orphan_imports.count() == 0
    page.close()
