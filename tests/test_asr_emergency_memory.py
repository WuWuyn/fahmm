import threading
import time
from types import SimpleNamespace

import pytest
from test_asr_jobs import hanging_worker, prepared_job, quick_worker

from fahmm import asr_jobs
from fahmm.asr import ASR_ERROR_MESSAGES

MIB = 1024 * 1024


def completed_then_hanging_worker(audio, model, language, output, cancel, start_seconds):
    output.put({"type": "started", "info": {"duration": 1, "language": language}})
    output.put({"type": "completed"})
    time.sleep(30)


@pytest.mark.parametrize(
    ("reading", "expected"),
    [
        (lambda: SimpleNamespace(available=76 * MIB), "asr_memory_low"),
        (lambda: (_ for _ in ()).throw(OSError("private path")), "asr_memory_unavailable"),
    ],
)
def test_unsafe_initial_memory_stops_owned_worker_and_keeps_old_data(
    tmp_path, monkeypatch, reading, expected
):
    monkeypatch.setattr(asr_jobs.psutil, "virtual_memory", reading)
    job, meeting, model_id, prior = prepared_job(tmp_path, hanging_worker)
    audio = job.library.audio_path(meeting)
    audio_before = audio.read_bytes()
    job.start(meeting, model_id)
    job.wait(10)
    snapshot = job.snapshot()
    assert snapshot.state == "error"
    assert snapshot.error_code == expected
    assert snapshot.error == ASR_ERROR_MESSAGES[expected]
    assert not job._process.is_alive()
    assert audio.read_bytes() == audio_before
    assert (prior / "working.json").read_text(encoding="utf-8") == "previous edits"


def test_emergency_during_inference_stops_worker_and_keeps_old_data(tmp_path, monkeypatch):
    low_memory = threading.Event()
    monkeypatch.setattr(
        asr_jobs.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=(76 if low_memory.is_set() else 2500) * MIB),
    )
    job, meeting, model_id, prior = prepared_job(tmp_path, hanging_worker)
    job.start(meeting, model_id)
    deadline = time.monotonic() + 10
    while job.snapshot().state != "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert job.snapshot().state == "running"
    low_memory.set()
    job.wait(10)
    assert job.snapshot().state == "error"
    assert job.snapshot().error_code == "asr_memory_low"
    assert not job._process.is_alive()
    assert job.library.audio_path(meeting).exists()
    assert (prior / "working.json").read_text(encoding="utf-8") == "previous edits"


def test_normal_short_audio_does_not_require_five_gib(tmp_path, monkeypatch):
    monkeypatch.setattr(
        asr_jobs.psutil, "virtual_memory", lambda: SimpleNamespace(available=2500 * MIB)
    )
    job, meeting, model_id, prior = prepared_job(tmp_path, quick_worker)
    job.start(meeting, model_id)
    job.wait(10)
    assert job.snapshot().state == "completed"
    assert (prior / "working.json").exists()


@pytest.mark.parametrize("after_cancel", [False, True])
def test_memory_emergency_takes_precedence_over_completion_and_cancel(
    tmp_path, monkeypatch, after_cancel
):
    low_memory = threading.Event()
    monkeypatch.setattr(
        asr_jobs.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=(76 if low_memory.is_set() else 2500) * MIB),
    )
    job, meeting, model_id, prior = prepared_job(tmp_path, completed_then_hanging_worker)
    job.start(meeting, model_id)
    deadline = time.monotonic() + 10
    while job.snapshot().state != "running" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert job.snapshot().state == "running"
    low_memory.set()
    if after_cancel:
        job.cancel()
    job.wait(10)
    assert job.snapshot().state == "error"
    assert job.snapshot().error_code == "asr_memory_low"
    assert not job._process.is_alive()
    assert (prior / "working.json").read_text(encoding="utf-8") == "previous edits"
