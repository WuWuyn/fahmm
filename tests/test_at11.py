"""AT-11: external UTF-8 exports and exact-scope deletion for both meeting sources."""

import os
import subprocess
import sys
import uuid

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
from test_media import make_audio
from test_meetings_page import select_meeting
from test_minutes_store import sample_content

from fahmm.media import import_audio
from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel, ModelManager
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def _saved_vietnamese_run(store, meeting_id, model_path):
    run_id = uuid.uuid4().hex
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, model_path
    )
    TranscriptStore(store).save_run(
        meeting_id,
        run_id,
        model,
        "vi",
        {"duration": 3},
        [{"id": 1, "start": 0.0, "end": 2.0, "text": "Đã thống nhất thử nghiệm."}],
    )
    version = MinutesStore(store).save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    return run_id, version


def _read_outside_app(path):
    return subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import pathlib,sys; "
            + "sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",
            str(path),
        ],
        text=True,
        encoding="utf-8",
    )


def test_at11_imported_and_recorded_exports_and_deletion(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    source = tmp_path / "original.wav"
    make_audio(source)
    source_bytes = source.read_bytes()
    store = MeetingStore(tmp_path / "meetings")
    imported = import_audio(store, source)
    recorded = store.create({})
    store.write_chunk(recorded, "microphone", 0, np.ones(4800, dtype=np.float32) * 0.1)
    store.finalize(recorded)
    for meeting_id in (imported, recorded):
        (store._meeting_dir(meeting_id) / ".interrupted.tmp").write_bytes(b"temporary")
        run_id, version = _saved_vietnamese_run(store, meeting_id, tmp_path / "model")
        folder = tmp_path / f"export-{meeting_id}"
        folder.mkdir()
        exporter = MeetingExportService(store)
        exporter.export_transcript(meeting_id, run_id, folder / "transcript.txt")
        exporter.export_minutes(meeting_id, version, folder / "minutes.md")
        assert "Đã thống nhất thử nghiệm." in _read_outside_app(folder / "transcript.txt")
        assert "Đã thống nhất thử nghiệm." in _read_outside_app(folder / "minutes.md")

    page = MeetingsPage(store, ModelManager(tmp_path / "models"))
    select_meeting(page, imported)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    page.delete_button.click()
    assert store._meeting_dir(imported).exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_button.click()
    assert not store._meeting_dir(imported).exists()
    assert not (store.root / f".deleting-{imported}").exists()
    assert store._meeting_dir(recorded).exists()
    assert source.read_bytes() == source_bytes
    select_meeting(page, recorded)
    page.delete_button.click()
    assert not store._meeting_dir(recorded).exists()
    assert not (store.root / f".deleting-{recorded}").exists()
    assert page.meeting_list.count() == 0
    assert source.read_bytes() == source_bytes
    for meeting_id in (imported, recorded):
        assert (tmp_path / f"export-{meeting_id}" / "minutes.md").is_file()
    page.close()
