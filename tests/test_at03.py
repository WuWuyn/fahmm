"""Optional full-length, blocked-network M2 acceptance test (AT-03)."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from test_asr import blocked_worker

from fahmm.asr_jobs import ASRJobController
from fahmm.media import probe_audio
from fahmm.models import ModelManager
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore
from legacy.qt.meetings_page import MeetingsPage

os.environ["QT_QPA_PLATFORM"] = "offscreen"
_APP_HOLDER = []


def test_at03_offline_vietnamese_long_recording(tmp_path, monkeypatch):
    default = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "fahmm"
        / "acceptance"
        / ("vi-vn-fleurs-dev-30m.wav")
    )
    sample = Path(os.environ.get("FAHMM_AT03_AUDIO", default))
    if not sample.is_file():
        pytest.skip("Set FAHMM_AT03_AUDIO to a licensed 30–60-minute Vietnamese file")
    model = ModelManager().selected()
    if model is None or model.repository != "Systran/faster-whisper-base":
        pytest.skip("Install and select the multilingual Base model for AT-03")
    info = probe_audio(sample)
    assert 1800 <= info.seconds <= 3600

    if os.environ.get("FAHMM_AT03_CHILD") != "1":
        # Keep the long native ASR/Qt lifecycle separate from the rest of pytest on Windows.
        with tempfile.TemporaryDirectory(prefix="fahmm-at03-pytest-") as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    f"{Path(__file__).resolve()}::test_at03_offline_vietnamese_long_recording",
                    f"--basetemp={directory}",
                ],
                env={**os.environ, "FAHMM_AT03_CHILD": "1"},
                capture_output=True,
                text=True,
                timeout=2100,
                check=False,
            )
        assert result.returncode == 0 and "1 passed" in result.stdout, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        return

    app = QApplication.instance() or QApplication([])
    _APP_HOLDER.append(app)
    assert app
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    store = MeetingStore(tmp_path / "meetings")
    jobs = ASRJobController(store, ModelManager(), worker_target=blocked_worker)
    page = MeetingsPage(store, ModelManager(), jobs)
    page.show()
    page.import_file(sample)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and (page._import_busy or page.meeting_list.count() == 0):
        QTest.qWait(100)
        if warnings:
            break
    assert page.meeting_list.count() == 1, (page.status_label.text(), page._import_busy, warnings)
    page.meeting_list.setCurrentRow(0)
    assert page.language_box.currentData() == "vi"
    responsive_ticks = []
    QTimer.singleShot(100, lambda: responsive_ticks.append(True))
    page.transcribe_button.click()
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline and jobs.snapshot().state not in ("completed", "error"):
        QTest.qWait(100)
    assert jobs.snapshot().state == "completed", jobs.snapshot()
    jobs.wait(10)
    assert jobs._monitor_thread is not None and not jobs._monitor_thread.is_alive()
    assert responsive_ticks
    meeting_id = page._selected_id()
    data = TranscriptStore(store).active_run(meeting_id)
    assert data is not None
    assert data["manifest"]["selected_language"] == "vi"
    assert data["manifest"]["model_repository"] == "Systran/faster-whisper-base"
    assert len(data["original"]) > 0
    assert all(0 <= s["start"] <= s["end"] <= info.seconds + 1 for s in data["original"])
    assert store.metadata(meeting_id)["privacy_mode"] == "restricted"
    page.close()
