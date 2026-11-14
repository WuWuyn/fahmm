"""Exercise recording adapters with fake devices and durable recovery data."""

import time
import wave
from contextlib import contextmanager

import numpy as np

from fahmm.audio import AudioDevice
from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.controller import SessionController
from fahmm.storage import SAMPLE_RATE


class FakeCapture:
    def list_devices(self):
        return {
            "system": [AudioDevice("speaker", "Speaker")],
            "microphone": [AudioDevice("mic", "Microphone")],
        }

    @contextmanager
    def open(self, source, device_id):
        assert device_id == {"system": "speaker", "microphone": "mic"}[source]

        class Stream:
            def read(self, frames):
                time.sleep(frames / SAMPLE_RATE)
                return np.full(frames, 0.25, dtype=np.float32)

        yield Stream()


def call(app, operation, **params):
    frame = {"v": 1, "kind": "request", "id": "test", "op": operation, "params": params}
    reply = app.handle(frame)
    encode_frame(reply)
    assert reply["kind"] == "response"
    return reply["result"]


def await_recording_state(app, expected):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = call(app, "recording.snapshot")
        if snapshot["state"] == expected:
            return snapshot
        time.sleep(0.02)
    raise AssertionError(f"Expected {expected}, got {snapshot}")


def test_bridge_record_pause_resume_stop(tmp_path):
    app = BridgeApplication(tmp_path)
    app.recorder = SessionController(FakeCapture(), app.store)
    call(app, "session.hello", versions=[1])
    devices = call(app, "recording.devices")
    assert devices["system"] == [{"id": "speaker", "name": "Speaker"}]
    meeting = call(app, "recording.start", systemId="speaker", microphoneId="mic")["meetingId"]
    await_recording_state(app, "recording")
    time.sleep(0.1)
    levels = call(app, "recording.snapshot")["levels"]
    assert levels["system"] > 0 and levels["microphone"] > 0
    assert call(app, "recording.pause")["state"] == "paused"
    assert call(app, "recording.snapshot")["levels"] == {"system": 0.0, "microphone": 0.0}
    seconds = call(app, "recording.snapshot")["seconds"]
    time.sleep(0.1)
    assert abs(call(app, "recording.snapshot")["seconds"] - seconds) < 0.02
    assert call(app, "recording.resume")["state"] == "recording"
    time.sleep(0.1)
    assert call(app, "recording.stop")["state"] == "finalizing"
    assert await_recording_state(app, "completed")["meetingId"] == meeting
    assert call(app, "recording.incomplete")["meetings"] == []
    assert "recording" not in call(app, "recording.snapshot")


def test_bridge_recovers_committed_chunks_after_restart(tmp_path):
    first = BridgeApplication(tmp_path)
    meeting = first.store.create({"system": "speaker", "microphone": "mic"})
    first.store.write_chunk(meeting, "system", 0, np.full(1000, 0.25, dtype=np.float32))
    first.store.write_chunk(meeting, "microphone", 0, np.full(1000, -0.25, dtype=np.float32))
    del first

    restarted = BridgeApplication(tmp_path)
    call(restarted, "session.hello", versions=[1])
    assert [item["id"] for item in call(restarted, "recording.incomplete")["meetings"]] == [meeting]
    assert call(restarted, "recording.recover", meetingId=meeting)["state"] == "finalizing"
    await_recording_state(restarted, "completed")
    with wave.open(str(restarted.library.audio_path(meeting)), "rb") as audio:
        assert audio.getnframes() == 1000
        assert audio.getnchannels() == 2
    assert call(restarted, "recording.incomplete")["meetings"] == []
