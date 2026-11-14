"""Verify the earlier Qt candidate can reopen data written by the Tauri core."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

import numpy as np

from fahmm.models import InstalledModel, ModelManager
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "release/fahmm-0.1.0-windows-x64.zip"
CHECKSUM = ARCHIVE.with_suffix(ARCHIVE.suffix + ".sha256")


def verify() -> None:
    expected = CHECKSUM.read_text(encoding="ascii").split()[0].lower()
    with ARCHIVE.open("rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == expected
    with tempfile.TemporaryDirectory(prefix="fahmm-rollback-") as directory:
        root = Path(directory)
        with zipfile.ZipFile(ARCHIVE) as package:
            for name in package.namelist():
                parts = Path(name).parts
                assert parts and parts[0] == "fahmm" and ".." not in parts
            package.extractall(root / "old")
        legacy_exe = root / "old" / "fahmm" / "fahmm.exe"
        assert legacy_exe.is_file()
        store = MeetingStore(root / "fahmm" / "meetings")
        meeting = store.create({"system": "speaker", "microphone": "mic"})
        store.write_chunk(meeting, "system", 0, np.ones(48_000, dtype=np.float32) * 0.1)
        store.finalize(meeting)
        run_id = uuid.uuid4().hex
        model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, root)
        TranscriptStore(store).save_run(meeting, run_id, model, "vi", {"duration": 1}, [
            {"id": 1, "start": 0, "end": 1, "text": "Nội dung tiếng Việt"},
        ])
        OfflineMinutesService(store).generate(meeting)
        env = {**os.environ, "LOCALAPPDATA": directory, "QT_QPA_PLATFORM": "offscreen"}
        result = subprocess.run([str(legacy_exe), "--smoke"], env=env, capture_output=True,
                                timeout=90, check=False)
        assert result.returncode == 0, f"Legacy app could not open saved data: {result.returncode}"
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from legacy.qt.meetings_page import MeetingsPage

        app = QApplication([])
        page = MeetingsPage(store, ModelManager(root / "fahmm" / "models"))
        rows = [page.meeting_list.item(index).data(Qt.UserRole)
                for index in range(page.meeting_list.count())]
        assert meeting in rows
        page.meeting_list.setCurrentRow(rows.index(meeting))
        assert page._selected_id() == meeting
        assert page.minutes_panel.meeting_id == meeting
        page.close()
        app.quit()
    print("Earlier Qt candidate reopened a saved meeting: PASS")


if __name__ == "__main__":
    verify()
