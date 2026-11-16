"""AT-05: controlled local recording through offline ASR and minutes."""

import os
import socket
import time
import wave
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
from test_asr import blocked_worker
from test_controller import FakeCapture, await_state

from fahmm.asr_jobs import ASRJobController
from fahmm.controller import SessionController, State
from fahmm.models import ModelManager
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


class FixtureStream:
    def __init__(self, samples):
        self.samples = samples
        self.position = 0

    def read(self, frames):
        time.sleep(frames / 48_000)
        chunk = self.samples[self.position : self.position + frames]
        self.position += frames
        if len(chunk) < frames:
            chunk = np.pad(chunk, (0, frames - len(chunk)))
        return chunk.astype(np.float32)


class SpeechCapture(FakeCapture):
    def __init__(self, samples):
        super().__init__()
        self.samples = samples

    @contextmanager
    def open(self, source, device_id):
        assert device_id == {"system": "speaker", "microphone": "mic"}[source]
        samples = self.samples if source == "system" else np.zeros_like(self.samples)
        yield FixtureStream(samples)


def test_at05_record_asr_offline_draft_without_content_egress(tmp_path, monkeypatch):
    sample = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "fahmm"
        / "acceptance"
        / ("vi-vn-fleurs-dev-30m.wav")
    )
    model = ModelManager().selected()
    if not sample.is_file() or model is None or model.repository != "Systran/faster-whisper-base":
        pytest.skip("AT-05 requires the licensed Vietnamese sample and installed Base model")
    with wave.open(str(sample), "rb") as file:
        assert file.getframerate() == 16_000 and file.getnchannels() == 1
        speech = np.frombuffer(file.readframes(16_000 * 12), dtype="<i2") / 32768.0
    speech_48k = np.repeat(speech, 3)
    network_attempts = []

    def block_network(*_args, **_kwargs):
        network_attempts.append(True)
        raise AssertionError("Meeting content attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", block_network)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    store = MeetingStore(tmp_path / "meetings")
    controller = SessionController(SpeechCapture(speech_48k), store)
    meeting_id = controller.start("speaker", "mic")
    await_state(controller, State.RECORDING)
    time.sleep(9)
    controller.stop()
    await_state(controller, State.COMPLETED, timeout=15)
    jobs = ASRJobController(store, ModelManager(), worker_target=blocked_worker)
    jobs.start(meeting_id, model.id, "vi")
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and jobs.snapshot().state not in ("completed", "error"):
        time.sleep(0.1)
    assert jobs.snapshot().state == "completed", jobs.snapshot()
    run = TranscriptStore(store).active_run(meeting_id)
    assert run and run["working"]
    version_id = OfflineMinutesService(store).generate(meeting_id)
    content = OfflineMinutesService(store).minutes.read_version(meeting_id, version_id)["content"]
    assert content["label"] == "Unverified · Offline extractive draft"
    assert content["topics"][0]["sources"]
    assert store.privacy_mode(meeting_id) == "restricted"
    assert network_attempts == []
