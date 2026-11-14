import os
import time
import uuid

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_asr_jobs import quick_worker
from test_media import make_audio
from test_models import make_bundle

from fahmm.asr_jobs import ASRJobController
from fahmm.models import InstalledModel, ModelManager
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def wait_until(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        QTest.qWait(30)
        if predicate():
            return
    raise AssertionError("Timed out waiting for meeting action")


def select_meeting(page, meeting_id):
    for row in range(page.meeting_list.count()):
        item = page.meeting_list.item(row)
        if item.data(Qt.UserRole) == meeting_id:
            page.meeting_list.setCurrentItem(item)
            return
    raise AssertionError("Meeting missing from list")


def test_imported_and_recorded_meetings_reopen_and_transcribe(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    assert app
    store = MeetingStore(tmp_path / "meetings")
    recorded = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(recorded, "system", 0, np.ones(1000))
    store.finalize(recorded)
    models = ModelManager(tmp_path / "models")
    model_id = uuid.uuid4().hex
    model_path = models._path(model_id)
    make_bundle(model_path)
    models._register(InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40,
                                    20, model_path))
    second_id = uuid.uuid4().hex
    second_path = models._path(second_id)
    make_bundle(second_path)
    models._register(InstalledModel(second_id, "test/whisper-2", "test", "MIT", "b" * 40,
                                    20, second_path))
    jobs = ASRJobController(store, models, worker_target=quick_worker)
    page = MeetingsPage(store, models, jobs)
    page.show()
    source = tmp_path / "imported.mp3"
    make_audio(source)
    page.import_file(source)
    wait_until(lambda: page.meeting_list.count() == 2 and not page._import_busy)
    imported = next(item.id for item in page.library.list_meetings()
                    if item.source_kind == "imported")
    page.library.rename(imported, "Interview")
    page.refresh(selected_id=imported)
    played = []
    monkeypatch.setattr(page.player, "play", lambda path, *args: played.append(path))
    page.play_button.click()
    assert played and played[0].suffix == ".mp3"
    page.language_box.setCurrentIndex(2)
    page.transcribe_button.click()
    wait_until(lambda: jobs.snapshot().state == "completed")
    wait_until(lambda: page.segment_table.rowCount() == 1)
    first_run = store.metadata(imported)["active_run"]
    page.segment_table.item(0, 1).setText("Corrected text")
    assert page.save_transcript_button.isEnabled()
    page.save_transcript_button.click()
    assert page.transcripts.read_run(imported, first_run)["working"][0]["text"] == "Corrected text"
    page.segment_table.setCurrentCell(0, 1)
    page.play_segment_button.click()
    assert len(played) == 2
    page.model_box.setCurrentIndex(page.model_box.findData(second_id))
    page.transcribe_button.click()
    page._tick()
    wait_until(lambda: jobs.snapshot().state == "completed" and page.run_box.count() == 2)
    assert store.metadata(imported)["active_run"] != first_run
    page.run_box.setCurrentIndex(page.run_box.findData(first_run))
    assert page.segment_table.item(0, 1).text() == "Corrected text"
    page.segment_table.setCurrentCell(0, 1)
    assert "Hello" in page.original_label.text()
    assert TranscriptStore(store).active_run(imported)["working"][0]["text"] == "Corrected text"
    page.close()

    reopened_store = MeetingStore(store.root)
    reopened_models = ModelManager(models.root)
    reopened_jobs = ASRJobController(reopened_store, reopened_models, worker_target=quick_worker)
    reopened = MeetingsPage(reopened_store, reopened_models, reopened_jobs)
    reopened.show()
    assert {item.id for item in reopened.library.list_meetings()} == {recorded, imported}
    assert reopened.library.get(imported).name == "Interview"
    select_meeting(reopened, imported)
    assert reopened.segment_table.item(0, 1).text() == "Corrected text"
    select_meeting(reopened, recorded)
    reopened.transcribe_button.click()
    wait_until(lambda: reopened_jobs.snapshot().state == "completed")
    assert TranscriptStore(reopened_store).active_run(recorded)["working"][0]["text"] == "Hello"
    reopened.close()
