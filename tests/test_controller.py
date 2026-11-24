import socket
import threading
import time
import wave
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

import fahmm.controller as controller_module
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


class ManualClock:
    def __init__(self):
        self._value = 100.0
        self._lock = threading.Lock()

    def monotonic(self):
        with self._lock:
            return self._value

    def advance(self, seconds):
        with self._lock:
            self._value += seconds


class GatedCapture(FakeCapture):
    """A device that holds each read until the test releases it."""

    def __init__(self, failing_source=None):
        super().__init__()
        self.failing_source = failing_source
        self.started = {
            source: [threading.Event(), threading.Event()] for source in ("system", "microphone")
        }
        self.release = {
            source: [threading.Event(), threading.Event()] for source in ("system", "microphone")
        }
        self.counts = {source: 0 for source in self.started}
        self.lock = threading.Lock()

    @contextmanager
    def open(self, source, device_id):
        assert device_id == {"system": "speaker", "microphone": "mic"}[source]
        capture = self

        class GatedStream:
            def read(self, frames):
                with capture.lock:
                    index = capture.counts[source]
                    capture.counts[source] += 1
                if index >= 2:
                    raise AssertionError("Unexpected extra capture read")
                capture.started[source][index].set()
                if not capture.release[source][index].wait(5):
                    raise TimeoutError("Test did not release capture read")
                if source == capture.failing_source:
                    raise RuntimeError("device disconnected")
                return np.full(frames, 0.25 if source == "system" else -0.25, dtype=np.float32)

        yield GatedStream()

    def wait_read(self, index):
        for source in self.started:
            assert self.started[source][index].wait(5)

    def release_read(self, index):
        for source in self.release:
            self.release[source][index].set()

    def release_all(self):
        for events in self.release.values():
            for event in events:
                event.set()


@pytest.mark.parametrize("pause_before_stop", [False, True])
def test_delayed_read_keeps_only_samples_before_stop_for_both_sources(
    tmp_path, monkeypatch, pause_before_stop
):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    capture = GatedCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        capture.wait_read(0)
        clock.advance(0.02)
        if pause_before_stop:
            controller.pause()
            clock.advance(0.5)  # Paused wall time must not extend the recording.
        controller.stop()
        cutoff = controller._capture_cutoffs[0]
        capture.release_read(0)
        controller.wait(10)
        assert controller.snapshot().state == State.COMPLETED
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped and 950 <= cutoff <= 960
        for source in ("system", "microphone"):
            assert len(chunks[source]) == 1
            assert chunks[source][0].start_frame == 0
            assert chunks[source][0].frames == cutoff
        with wave.open(str(controller.snapshot().recording), "rb") as output:
            assert output.getnframes() == cutoff
            stereo = np.frombuffer(output.readframes(cutoff), dtype="<i2").reshape(-1, 2)
        assert np.all(stereo[:, 0] > 0) and np.all(stereo[:, 1] < 0)
    finally:
        capture.release_all()
        controller.wait(5)


@pytest.mark.parametrize("pause_twice", [False, True])
def test_pause_resume_during_read_uses_original_epoch_cutoff(tmp_path, monkeypatch, pause_twice):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    capture = GatedCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        capture.wait_read(0)
        clock.advance(0.02)
        controller.pause()
        first_cutoff = controller._capture_cutoffs[0]
        clock.advance(0.3)
        controller.resume()  # Resume before either pending read returns.
        if pause_twice:
            clock.advance(0.01)
            controller.pause()
            clock.advance(0.2)
            controller.resume()
        second_start = int(controller.snapshot().seconds * 48_000)
        capture.release_read(0)
        capture.wait_read(1)
        clock.advance(0.02)
        controller.stop()
        final_cutoff = controller._capture_cutoffs[controller._capture_epoch - 1]
        capture.release_read(1)
        controller.wait(10)
        assert controller.snapshot().state == State.COMPLETED
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped and 950 <= first_cutoff <= 960
        for source in ("system", "microphone"):
            assert len(chunks[source]) == 2
            first, second = chunks[source]
            assert first.start_frame == 0 and first.frames == first_cutoff
            assert abs(second.start_frame - second_start) <= 1
            assert second.frames > 0
            assert second.start_frame + second.frames <= final_cutoff
        with wave.open(str(controller.snapshot().recording), "rb") as output:
            assert output.getnframes() == final_cutoff
    finally:
        capture.release_all()
        controller.wait(5)


def gate_two_level_calculations(monkeypatch):
    sqrt = np.sqrt
    both_appended = threading.Barrier(3)
    release_level = threading.Event()
    blocked_threads: set[int] = set()
    blocked_lock = threading.Lock()

    def gated_sqrt(value):
        thread_id = threading.get_ident()
        with blocked_lock:
            should_wait = thread_id not in blocked_threads and len(blocked_threads) < 2
            if should_wait:
                blocked_threads.add(thread_id)
        if should_wait:
            both_appended.wait(timeout=5)
            if not release_level.wait(5):
                raise TimeoutError("Test did not release input-level calculation")
        return sqrt(value)

    monkeypatch.setattr(controller_module.np, "sqrt", gated_sqrt)
    return both_appended, release_level


def test_pause_resume_after_read_still_flushes_the_old_epoch(tmp_path, monkeypatch):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    capture = GatedCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    both_appended, release_level = gate_two_level_calculations(monkeypatch)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        capture.wait_read(0)
        clock.advance(2048 / 48_000)
        capture.release_read(0)
        both_appended.wait(timeout=5)  # Both completed reads are already buffered.
        clock.advance(0.01)
        controller.pause()
        first_cutoff = controller._capture_cutoffs[0]
        clock.advance(0.3)
        controller.resume()
        release_level.set()
        capture.wait_read(1)
        clock.advance(0.02)
        controller.stop()
        final_cutoff = controller._capture_cutoffs[1]
        capture.release_read(1)
        controller.wait(10)
        assert controller.snapshot().state == State.COMPLETED
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped
        for source in ("system", "microphone"):
            assert len(chunks[source]) == 2
            first, second = chunks[source]
            assert first.start_frame == 0 and first.frames == 2048
            assert abs(second.start_frame - first_cutoff) <= 1
            assert second.start_frame + second.frames <= final_cutoff
    finally:
        release_level.set()
        capture.release_all()
        controller.wait(5)


@pytest.mark.parametrize("resume_after_pause", [False, True])
def test_early_block_already_buffered_is_trimmed_on_stop_or_pause(
    tmp_path, monkeypatch, resume_after_pause
):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    capture = GatedCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    both_appended, release_level = gate_two_level_calculations(monkeypatch)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        capture.wait_read(0)
        capture.release_read(0)  # Complete a full block before the clock advances.
        both_appended.wait(timeout=5)
        clock.advance(0.01)
        if resume_after_pause:
            controller.pause()
        else:
            controller.stop()
        first_cutoff = controller._capture_cutoffs[0]
        assert 470 <= first_cutoff <= 480
        if resume_after_pause:
            clock.advance(0.3)
            controller.resume()
        release_level.set()
        if resume_after_pause:
            capture.wait_read(1)
            clock.advance(0.02)
            controller.stop()
            capture.release_read(1)
        controller.wait(10)
        assert controller.snapshot().state == State.COMPLETED
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped
        for source in ("system", "microphone"):
            assert chunks[source][0].start_frame == 0
            assert chunks[source][0].frames == first_cutoff
            if resume_after_pause:
                assert len(chunks[source]) == 2
                assert abs(chunks[source][1].start_frame - first_cutoff) <= 1
            else:
                assert len(chunks[source]) == 1
        if not resume_after_pause:
            with wave.open(str(controller.snapshot().recording), "rb") as output:
                assert output.getnframes() == first_cutoff
    finally:
        release_level.set()
        capture.release_all()
        controller.wait(5)


@pytest.mark.parametrize("pause_before_stop", [False, True])
def test_ahead_buffer_over_two_seconds_is_not_committed_past_cutoff(
    tmp_path, monkeypatch, pause_before_stop
):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))

    class AheadCapture(FakeCapture):
        def __init__(self):
            super().__init__()
            self.waiting = {source: threading.Event() for source in ("system", "microphone")}
            self.release = threading.Event()

        @contextmanager
        def open(self, source, _device):
            capture = self

            class AheadStream:
                reads = 0

                def read(self, frames):
                    self.reads += 1
                    if self.reads == 48:
                        capture.waiting[source].set()
                        if not capture.release.wait(5):
                            raise TimeoutError("Test did not release early audio")
                    return np.full(frames, 0.25 if source == "system" else -0.25, np.float32)

            yield AheadStream()

    capture = AheadCapture()
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        for event in capture.waiting.values():
            assert event.wait(5)
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped and not any(chunks.values())  # No future frames committed.
        clock.advance(0.5)
        if pause_before_stop:
            controller.pause()
        else:
            controller.stop()
        cutoff = controller._capture_cutoffs[0]
        capture.release.set()
        if pause_before_stop:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if all(store.scan_chunks(meeting)[0].values()):
                    break
                time.sleep(0.01)
            clock.advance(1.0)
            controller.stop()
        controller.wait(10)
        assert controller.snapshot().state == State.COMPLETED
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped and 23_999 <= cutoff <= 24_000
        for source in ("system", "microphone"):
            assert len(chunks[source]) == 1
            assert chunks[source][0].start_frame == 0 and chunks[source][0].frames == cutoff
        with wave.open(str(controller.snapshot().recording), "rb") as output:
            assert output.getnframes() == cutoff
    finally:
        capture.release.set()
        controller.wait(5)


def test_device_running_ahead_is_bounded_and_reports_error(tmp_path, monkeypatch):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))

    class FastCapture(FakeCapture):
        @contextmanager
        def open(self, _source, _device):
            class FastStream:
                def read(self, frames):
                    return np.ones(frames, dtype=np.float32)

            yield FastStream()

    store = MeetingStore(tmp_path)
    controller = SessionController(FastCapture(), store)
    meeting = controller.start("speaker", "mic")
    error = await_state(controller, State.ERROR)
    controller.wait(10)
    assert "exceeded the recording clock" in error.error
    chunks, skipped = store.scan_chunks(meeting)
    assert not skipped and not any(chunks.values())


def test_device_failure_preserves_other_source_before_failure(tmp_path, monkeypatch):
    clock = ManualClock()
    monkeypatch.setattr(controller_module, "time", SimpleNamespace(monotonic=clock.monotonic))
    capture = GatedCapture(failing_source="microphone")
    store = MeetingStore(tmp_path)
    controller = SessionController(capture, store)
    meeting = controller.start("speaker", "mic")
    try:
        await_state(controller, State.RECORDING)
        capture.wait_read(0)
        clock.advance(0.02)
        capture.release["microphone"][0].set()
        await_state(controller, State.ERROR)
        cutoff = controller._capture_cutoffs[0]
        capture.release["system"][0].set()
        controller.wait(10)
        chunks, skipped = store.scan_chunks(meeting)
        assert not skipped and len(chunks["system"]) == 1 and not chunks["microphone"]
        assert chunks["system"][0].frames == cutoff > 0
        assert store.metadata(meeting)["state"] == "error"
        controller.recover(meeting)
        recovered = await_state(controller, State.COMPLETED)
        with wave.open(str(recovered.recording), "rb") as output:
            stereo = np.frombuffer(output.readframes(output.getnframes()), dtype="<i2").reshape(
                -1, 2
            )
        assert len(stereo) == cutoff
        assert np.all(stereo[:, 0] > 0) and np.all(stereo[:, 1] == 0)
    finally:
        capture.release_all()
        controller.wait(5)
