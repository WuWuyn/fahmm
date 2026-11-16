import os
import uuid

import numpy as np
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_media import make_audio
from test_meetings_page import select_meeting, wait_until

from fahmm.media import import_audio
from fahmm.models import InstalledModel, ModelManager
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_recorded_and_imported_minutes_review_survives_restart(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    store = MeetingStore(tmp_path / "meetings")
    recorded = store.create({})
    store.write_chunk(recorded, "system", 0, np.ones(2000))
    store.finalize(recorded)
    source = tmp_path / "source.mp3"
    make_audio(source)
    imported = import_audio(store, source)
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    transcripts = TranscriptStore(store)
    for meeting_id in (recorded, imported):
        transcripts.save_run(
            meeting_id,
            uuid.uuid4().hex,
            model,
            "vi",
            {"duration": 2},
            [
                {
                    "id": 1,
                    "start": 0,
                    "end": 1,
                    "text": "Chúng ta thống nhất thử nghiệm. Cần làm bản nháp.",
                }
            ],
        )
    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    page.show()
    played = []
    monkeypatch.setattr(page.player, "play", lambda path, *args: played.append((path, args)))
    approved = {}
    for meeting_id in (recorded, imported):
        select_meeting(page, meeting_id)
        panel = page.minutes_panel
        assert panel.mode_box.currentData() == "restricted"
        panel.mode_box.setCurrentIndex(panel.mode_box.findData("cloud_permitted"))
        assert store.privacy_mode(meeting_id) == "cloud_permitted"
        panel.mode_box.setCurrentIndex(panel.mode_box.findData("restricted"))
        assert store.privacy_mode(meeting_id) == "restricted"
        panel.offline_button.click()
        wait_until(lambda panel=panel: not panel._busy and panel.version_box.count() == 1)
        assert "Unverified" in panel.review_label.text()
        assert "Chưa rõ" in panel.content_edit.toPlainText()
        assert panel.citation_list.count() > 0
        panel.citation_list.setCurrentRow(0)
        panel.play_button.click()
        assert played[-1][0] == page.library.audio_path(meeting_id)
        assert page.segment_table.currentRow() == 0
        panel.content_edit.appendPlainText("User correction")
        panel.save_button.click()
        assert panel.version_box.count() == 2
        panel.approve_button.click()
        approved[meeting_id] = panel.version_box.currentData()
        assert "Approved" in panel.review_label.text()
        panel.offline_button.click()
        wait_until(lambda panel=panel: not panel._busy and panel.version_box.count() == 3)
        assert (
            panel.minutes.read_version(meeting_id, approved[meeting_id])["manifest"]["review_state"]
            == "approved"
        )
        assert (
            "User correction"
            in panel.minutes.read_version(meeting_id, approved[meeting_id])["content"]["user_text"]
        )
    page.close()
    reopened = MeetingsPage(MeetingStore(store.root), ModelManager(tmp_path / "models"))
    reopened.show()
    for meeting_id in (recorded, imported):
        select_meeting(reopened, meeting_id)
        panel = reopened.minutes_panel
        assert panel.version_box.count() == 3
        index = panel.version_box.findData(approved[meeting_id])
        panel.version_box.setCurrentIndex(index)
        assert "User correction" in panel.content_edit.toPlainText()
        assert panel.citation_list.count() > 0
    reopened.close()
    QTest.qWait(20)
