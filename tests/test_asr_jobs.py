import os
import time
import uuid

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_models import make_bundle

from fahmm.asr_jobs import ASRJobController
from fahmm.models import InstalledModel, ModelManager
from fahmm.storage import MeetingStore

os.environ["QT_QPA_PLATFORM"] = "offscreen"


def hanging_worker(audio, model, language, output, cancel, start_seconds):
    output.put({"type": "started", "info": {"duration": 100, "language": language}})
    time.sleep(30)


def crashed_worker(audio, model, language, output, cancel, start_seconds):
    os._exit(7)


def unsafe_error_worker(audio, model, language, output, cancel, start_seconds):
    output.put({"type": "error", "code": "cuda_vram", "message": "C:\\private\\meeting"})


def quick_worker(audio, model, language, output, cancel, start_seconds):
    output.put({"type": "started", "info": {"duration": 1, "language": language}})
    output.put({"type": "segment", "segment": {"id": 1, "start": 0, "end": 1, "text": "Hello"}})
    output.put({"type": "completed"})


def prepared_job(tmp_path, worker):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(meeting, "system", 0, np.ones(1000))
    store.finalize(meeting)
    prior = store._meeting_dir(meeting) / "transcripts" / "prior"
    prior.mkdir(parents=True)
    (prior / "working.json").write_text("previous edits", encoding="utf-8")
    models = ModelManager(tmp_path / "models")
    model_id = uuid.uuid4().hex
    model_path = models._path(model_id)
    make_bundle(model_path)
    models._register(
        InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 20, model_path)
    )
    return ASRJobController(store, models, worker_target=worker), meeting, model_id, prior


def test_cancel_hung_worker_keeps_ui_responsive_and_prior_data(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app
    job, meeting, model_id, prior = prepared_job(tmp_path, hanging_worker)
    job.start(meeting, model_id)
    ticks = []
    QTimer.singleShot(50, lambda: ticks.append(True))
    QTest.qWait(150)
    assert ticks
    job.cancel()
    job.wait(8)
    assert job.snapshot().state == "cancelled"
    assert (prior / "working.json").read_text(encoding="utf-8") == "previous edits"
    assert job.library.audio_path(meeting).exists()


def test_crash_reports_error_and_retry_succeeds(tmp_path):
    job, meeting, model_id, prior = prepared_job(tmp_path, crashed_worker)
    job.start(meeting, model_id)
    job.wait(10)
    assert job.snapshot().state == "error"
    assert "unexpectedly" in job.snapshot().error
    job.worker_target = quick_worker
    job.retry()
    job.wait(10)
    assert job.snapshot().state == "completed"
    assert job.snapshot().segment_count == 1
    assert (prior / "working.json").exists()


def test_cuda_worker_crash_is_distinct_and_preserves_previous_work(tmp_path, monkeypatch):
    monkeypatch.setenv("FAHMM_ASR_DEVICE", "cuda")
    job, meeting, model_id, prior = prepared_job(tmp_path, crashed_worker)
    job.start(meeting, model_id)
    job.wait(10)
    assert job.snapshot().state == "error"
    assert job.snapshot().error_code == "cuda_worker_crash"
    assert "unexpectedly" in job.snapshot().error
    assert (prior / "working.json").read_text(encoding="utf-8") == "previous edits"


def test_job_does_not_trust_worker_error_message(tmp_path):
    job, meeting, model_id, _ = prepared_job(tmp_path, unsafe_error_worker)
    job.start(meeting, model_id)
    job.wait(10)
    assert job.snapshot().state == "error"
    assert job.snapshot().error_code == "cuda_vram"
    assert "GPU memory" in job.snapshot().error
    assert "private" not in job.snapshot().error
