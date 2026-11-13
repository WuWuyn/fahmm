import socket
import time
import wave
from contextlib import contextmanager

import numpy as np

from fahmm.audio import AudioDevice
from fahmm.controller import SessionController, State
from fahmm.storage import MeetingStore


class FakeStream:
    def __init__(self, amplitude):
        self.amplitude = amplitude

    def read(self, frames):
        time.sleep(frames / 48_000)
        return np.full(frames, self.amplitude, dtype=np.float32)


class FakeCapture:
    def __init__(self, broken_source=None):
        self.broken_source = broken_source
        self.opened = []

    def list_devices(self):
        return {
            "system": [AudioDevice("speaker", "Speaker")],
            "microphone": [AudioDevice("mic", "Mic")],
        }

    @contextmanager
    def open(self, source, device_id):
        assert device_id == {"system": "speaker", "microphone": "mic"}[source]
        if source == self.broken_source:
            raise RuntimeError("unplugged")
        self.opened.append(source)
        yield FakeStream(0.5 if source == "system" else -0.5)


def await_state(controller, desired, timeout=5):
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        if controller.snapshot().state == desired:
            return controller.snapshot()
        time.sleep(0.02)
    raise AssertionError(f"Expected {desired}, got {controller.snapshot()}")


def test_record_pause_resume_stop_stays_local(tmp_path, monkeypatch):
    def forbid_network(*args, **kwargs):
        raise AssertionError("network request during local recording")

    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    capture = FakeCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    assert controller.snapshot().state == State.IDLE
    assert not capture.opened
    meeting = controller.start("speaker", "mic")
    await_state(controller, State.RECORDING)
    time.sleep(0.15)
    controller.pause()
    paused = controller.snapshot().seconds
    time.sleep(0.15)
    assert abs(controller.snapshot().seconds - paused) < 0.02
    controller.resume()
    time.sleep(0.15)
    controller.stop()
    final = await_state(controller, State.COMPLETED)
    assert final.recording.exists()
    assert final.seconds < 0.6
    with wave.open(str(final.recording), "rb") as file:
        assert file.getnchannels() == 2
        data = np.frombuffer(file.readframes(file.getnframes()), dtype="<i2").reshape(-1, 2)
    assert (data[:, 0] > 0).any() and (data[:, 1] < 0).any()
    assert store.metadata(meeting)["state"] == "completed"


def test_missing_device_does_not_report_recording(tmp_path):
    capture = FakeCapture(broken_source="microphone")
    controller = SessionController(capture, MeetingStore(tmp_path))
    controller.start("speaker", "mic")
    result = await_state(controller, State.ERROR)
    assert "microphone" in result.error
    assert result.recording is None


def test_stop_while_devices_are_starting_returns_promptly(tmp_path):
    class SlowCapture(FakeCapture):
        @contextmanager
        def open(self, source, device_id):
            time.sleep(0.2)
            with super().open(source, device_id) as stream:
                yield stream

    controller = SessionController(SlowCapture(), MeetingStore(tmp_path))
    controller.start("speaker", "mic")
    controller.stop()
    controller.wait(timeout=2)
    assert controller.snapshot().state == State.ERROR
    assert "Could not create the playback file" in controller.snapshot().error
