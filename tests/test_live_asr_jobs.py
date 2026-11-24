"""Lifecycle checks; live ASR is deliberately not wired into the desktop UI."""

from __future__ import annotations

import multiprocessing
import queue
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psutil
import pytest

from fahmm.audio import AudioDevice
from fahmm.controller import SessionController, State
from fahmm.live_asr import (
    CommittedChunkIndex,
    LiveCheckpoint,
    LiveConfig,
    LiveLease,
    run_live_asr_worker,
)
from fahmm.live_asr_jobs import LiveASRJobs, _live_cpu_threads
from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path, live_model_lock_path
from fahmm.storage import MeetingStore


class RecorderProbe:
    def __init__(self, store):
        self.store = store
        self.state = "writing"

    def capture_status(self, _meeting):
        return self.state


def test_live_cpu_thread_limit_is_bounded_and_validated(monkeypatch):
    monkeypatch.delenv("FAHMM_LIVE_CPU_THREADS", raising=False)
    monkeypatch.setattr("fahmm.live_asr_jobs.os.cpu_count", lambda: 12)
    assert _live_cpu_threads() == 4
    monkeypatch.setenv("FAHMM_LIVE_CPU_THREADS", "1")
    assert _live_cpu_threads() == 1
    monkeypatch.setenv("FAHMM_LIVE_CPU_THREADS", "5")
    with pytest.raises(ValueError, match="from 1 to 4"):
        _live_cpu_threads()


class ModelProbe:
    def __init__(self, root):
        self.root = root / "models"
        model_path = self.root / "installed" / ("b" * 32)
        model_path.mkdir(parents=True, exist_ok=True)
        self.model = SimpleNamespace(
            id="b" * 32, repository="test/base", revision="revision-1", path=model_path
        )
        self.held = 0

    def begin_use(self, model_id):
        assert model_id == self.model.id
        self.held += 1
        return self.model

    def end_use(self, model_id):
        assert model_id == self.model.id and self.held > 0
        self.held -= 1


def live_worker_fixture(directory, config, _model_path, output, cancel, finished):
    with LiveLease(Path(directory)):
        checkpoint = LiveCheckpoint(Path(directory), config)
        checkpoint.set_state("running")
        for number in range(100):
            try:
                output.put_nowait({"type": "progress", "cursor": 0, "available": number})
            except queue.Full:
                pass
        while not finished.is_set() and not cancel.is_set():
            time.sleep(0.01)
        if cancel.is_set():
            checkpoint.set_state("cancelled")
        else:
            index = CommittedChunkIndex(Path(directory))
            index.refresh()
            end = index.available_end(True)
            _audio, info = index.read(0, end)
            checkpoint.commit_window(0, end, [], info, index.new_chunks)
            checkpoint.set_state("completed")
        checkpoint.close()


def hanging_worker_fixture(directory, config, _model_path, _output, _cancel, _finished):
    with LiveLease(Path(directory)):
        checkpoint = LiveCheckpoint(Path(directory), config)
        checkpoint.set_state("running")
        while True:
            time.sleep(1)


def crashed_worker_fixture(directory, config, _model_path, _output, _cancel, _finished):
    with LiveLease(Path(directory)):
        checkpoint = LiveCheckpoint(Path(directory), config)
        checkpoint.set_state("running")
        checkpoint.close()
    raise SystemExit(7)


def worker_waits_for_early_cancel(directory, config, model_path, output, cancel, finished):
    while not cancel.is_set():
        time.sleep(0.005)
    run_live_asr_worker(
        directory,
        config,
        model_path,
        output,
        cancel,
        finished,
        model_factory=quiet_model_factory,
        model_validator=fake_model_validator,
    )


def review_worker_fixture(directory, config, _model_path, _output, _cancel, _finished):
    with LiveLease(Path(directory)):
        checkpoint = LiveCheckpoint(Path(directory), config)
        index = CommittedChunkIndex(Path(directory))
        index.refresh()
        end = index.available_end(True)
        _audio, info = index.read(0, end)
        info["boundary_review"] = True
        checkpoint.commit_window(
            0, end, [(0, end, "uncertain", "system", "provisional")], info, index.new_chunks
        )
        checkpoint.set_state("completed")  # A faulty worker cannot override review evidence.
        checkpoint.close()


def setup_job(tmp_path, worker=live_worker_fixture):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    for source in ("system", "microphone"):
        store.write_chunk(meeting, source, 0, np.full(1000, 0.3, np.float32))
    recorder = RecorderProbe(store)
    models = ModelProbe(tmp_path)
    jobs = LiveASRJobs(
        store,
        models,
        recorder,
        worker_target=worker,
        queue_size=1,
        poll_interval=0.05,
        cancel_timeout=0.3,
    )
    return store, meeting, recorder, models, jobs


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Condition did not become true")


def assert_exclusive_busy(path):
    with pytest.raises(TimeoutError):
        SharedFileLock(path, shared=False).acquire(timeout=0)


def assert_exclusive_available(path):
    lock = SharedFileLock(path, shared=False)
    lock.acquire(timeout=0)
    lock.release()


def test_live_job_holds_activity_and_model_until_real_capture_closed(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path)
    run_id = jobs.start(meeting, models.model.id)
    try:
        wait_until(lambda: jobs.snapshot().state == "running")
        assert models.held == 1
        assert "live_asr" in store.active_activities(meeting)
        meeting_lock = live_meeting_lock_path(store.root, meeting)
        model_lock = live_model_lock_path(models.root, models.model.id)
        assert_exclusive_busy(meeting_lock)
        assert_exclusive_busy(model_lock)
        with pytest.raises(RuntimeError, match="active meeting work"):
            store.begin_deletion(meeting)
        assert jobs.snapshot().run_id == run_id
        assert jobs.snapshot().capture_status == "writing"
        assert jobs.snapshot().state == "running"
        recorder.state = "closed"
        jobs.wait(10)
        assert jobs.snapshot().state == "completed"
        assert jobs.snapshot().cursor_seconds == pytest.approx(1000 / 48_000)
        assert models.held == 0
        assert "live_asr" not in store.active_activities(meeting)
        assert store.metadata(meeting).get("active_run") is None
        assert_exclusive_available(meeting_lock)
        assert_exclusive_available(model_lock)
    finally:
        jobs.cancel()
        jobs.wait(5)


def test_cancel_terminates_only_worker_and_keeps_checkpoint_resumable(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path, hanging_worker_fixture)
    run_id = jobs.start(meeting, models.model.id)
    try:
        wait_until(lambda: jobs.snapshot().state == "running")
        before = time.monotonic()
        jobs.cancel()
        jobs.wait(8)
        assert time.monotonic() - before < 5
        assert jobs.snapshot().state == "cancelled"
        assert models.held == 0
        assert "live_asr" not in store.active_activities(meeting)
        assert_exclusive_available(live_meeting_lock_path(store.root, meeting))
        assert_exclusive_available(live_model_lock_path(models.root, models.model.id))
        assert list((store._meeting_dir(meeting) / "system").glob("*.wav"))
        config = LiveCheckpoint.load_config(store._meeting_dir(meeting), run_id)
        saved = LiveCheckpoint(store._meeting_dir(meeting), config, create=False)
        assert saved.get("state") == "cancelled"
        saved.close()

        recorder.state = "closed"
        jobs.worker_target = live_worker_fixture
        assert jobs.resume(meeting, run_id) == run_id
        jobs.wait(10)
        assert jobs.snapshot().state == "completed"
        assert models.held == 0
    finally:
        jobs.cancel()
        jobs.wait(5)


def test_cancel_before_worker_acquires_locks_has_no_checkpoint_or_false_crash(tmp_path):
    store, meeting, _recorder, models, jobs = setup_job(tmp_path, worker_waits_for_early_cancel)
    run_id = jobs.start(meeting, models.model.id)
    jobs.cancel()
    jobs.wait(10)
    assert jobs.snapshot().state == "cancelled"
    assert jobs.snapshot().error_code is None
    assert not (store._meeting_dir(meeting) / "transcripts" / f".live-{run_id}").exists()
    assert models.held == 0 and store.active_activities(meeting) == ()
    assert_exclusive_available(live_meeting_lock_path(store.root, meeting))
    assert_exclusive_available(live_model_lock_path(models.root, models.model.id))


def test_capture_failure_cancels_worker_and_preserves_audio(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path, hanging_worker_fixture)
    jobs.start(meeting, models.model.id)
    try:
        wait_until(lambda: jobs.snapshot().state == "running")
        recorder.state = "failed"
        jobs.wait(10)
        assert jobs.snapshot().state == "error"
        assert jobs.snapshot().error_code == "live_capture_failed"
        assert models.held == 0
        assert "live_asr" not in store.active_activities(meeting)
        assert list((store._meeting_dir(meeting) / "system").glob("*.wav"))
    finally:
        jobs.cancel()
        jobs.wait(5)


def test_worker_crash_is_recorded_and_releases_resources(tmp_path):
    store, meeting, _recorder, models, jobs = setup_job(tmp_path, crashed_worker_fixture)
    run_id = jobs.start(meeting, models.model.id)
    jobs.wait(10)
    assert jobs.snapshot().state == "error"
    assert jobs.snapshot().error_code == "live_worker_crash"
    assert models.held == 0 and "live_asr" not in store.active_activities(meeting)
    config = LiveCheckpoint.load_config(store._meeting_dir(meeting), run_id)
    checkpoint = LiveCheckpoint(store._meeting_dir(meeting), config, create=False)
    assert checkpoint.get("state") == "error"
    assert checkpoint.get("error_code") == "live_worker_crash"
    checkpoint.close()


def test_provisional_output_cannot_be_reported_as_completed(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path, review_worker_fixture)
    recorder.state = "closed"
    run_id = jobs.start(meeting, models.model.id)
    jobs.wait(10)
    assert jobs.snapshot().state == "needs_review"
    assert jobs.snapshot().provisional_count == 1
    config = LiveCheckpoint.load_config(store._meeting_dir(meeting), run_id)
    checkpoint = LiveCheckpoint(store._meeting_dir(meeting), config, create=False)
    assert checkpoint.get("state") == "needs_review"
    checkpoint.close()
    assert models.held == 0


def test_unknown_capture_is_not_assumed_finished(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path)
    recorder.state = "unknown"
    with pytest.raises(RuntimeError, match="Recover the recording"):
        jobs.start(meeting, models.model.id)
    assert store.active_activities(meeting) == () and models.held == 0


@pytest.mark.parametrize("kind", ["meeting", "model"])
def test_parent_fails_safely_if_deletion_locked_resource_first(tmp_path, kind):
    store, meeting, _recorder, models, jobs = setup_job(tmp_path)
    meeting_path = live_meeting_lock_path(store.root, meeting)
    model_path = live_model_lock_path(models.root, models.model.id)
    deleting = SharedFileLock(meeting_path if kind == "meeting" else model_path, shared=False)
    deleting.acquire(timeout=0)
    try:
        with pytest.raises(TimeoutError):
            jobs.start(meeting, models.model.id)
        assert store.active_activities(meeting) == () and models.held == 0
        if kind == "model":
            assert_exclusive_available(meeting_path)
    finally:
        deleting.release()


def test_resume_rejects_model_revision_mismatch_and_releases_leases(tmp_path):
    store, meeting, _recorder, models, jobs = setup_job(tmp_path, hanging_worker_fixture)
    run_id = jobs.start(meeting, models.model.id)
    try:
        wait_until(lambda: jobs.snapshot().state == "running")
        jobs.cancel()
        jobs.wait(10)
        models.model.revision = "different"
        with pytest.raises(ValueError, match="does not match"):
            jobs.resume(meeting, run_id)
        assert models.held == 0
        assert "live_asr" not in store.active_activities(meeting)
    finally:
        jobs.cancel()
        jobs.wait(5)


class ControlledStream:
    def __init__(self, started, release):
        self.started, self.release = started, release
        self.count = 0

    def read(self, frames):
        self.count += 1
        if self.count > 1:
            self.started.set()
            self.release.wait(10)
        return np.full(frames, 0.25, np.float32)


class ControlledCapture:
    def __init__(self):
        self.started = {source: threading.Event() for source in ("system", "microphone")}
        self.release = {source: threading.Event() for source in ("system", "microphone")}

    def list_devices(self):
        return {
            "system": [AudioDevice("speaker", "Speaker")],
            "microphone": [AudioDevice("mic", "Microphone")],
        }

    @contextmanager
    def open(self, source, _device):
        yield ControlledStream(self.started[source], self.release[source])


def test_capture_status_waits_for_both_real_writers(tmp_path):
    capture = ControlledCapture()
    store = MeetingStore(tmp_path)
    recorder = SessionController(capture, store)
    meeting = recorder.start("speaker", "mic")
    try:
        wait_until(lambda: recorder.snapshot().state == State.RECORDING)
        assert capture.started["system"].wait(5)
        assert capture.started["microphone"].wait(5)
        assert recorder.capture_status(meeting) == "writing"
        recorder.stop()
        capture.release["system"].set()
        wait_until(lambda: not recorder._capture_threads[meeting][0].is_alive())
        assert recorder.capture_status(meeting) == "writing"
        capture.release["microphone"].set()
        wait_until(lambda: recorder.capture_status(meeting) == "closed")
        recorder.wait(10)
        assert store.metadata(meeting)["state"] == "completed"
    finally:
        for event in capture.release.values():
            event.set()
        recorder.wait(5)


class QuietModel:
    def transcribe(self, _audio):
        return []


def quiet_model_factory(_path, _config):
    return QuietModel()


def fake_model_validator(path, config):
    assert path.is_dir() and path.name == config.model_id


def real_live_worker_fixture(directory, config, model_path, output, cancel, finished):
    run_live_asr_worker(
        directory,
        config,
        model_path,
        output,
        cancel,
        finished,
        model_factory=quiet_model_factory,
        model_validator=fake_model_validator,
        poll_seconds=0.05,
    )


def test_parent_and_real_worker_hold_shared_locks_simultaneously(tmp_path):
    store, meeting, recorder, models, jobs = setup_job(tmp_path, real_live_worker_fixture)
    jobs.start(meeting, models.model.id)
    try:
        wait_until(lambda: jobs.snapshot().state == "running")
        assert_exclusive_busy(live_meeting_lock_path(store.root, meeting))
        assert_exclusive_busy(live_model_lock_path(models.root, models.model.id))
        recorder.state = "closed"
        jobs.wait(10)
        assert jobs.snapshot().state == "completed"
        assert_exclusive_available(live_meeting_lock_path(store.root, meeting))
        assert_exclusive_available(live_model_lock_path(models.root, models.model.id))
    finally:
        jobs.cancel()
        jobs.wait(5)


def _spawn_live_child(directory, config, model_path, pid_file):
    context = multiprocessing.get_context("spawn")
    cancel, finished = context.Event(), context.Event()
    child = context.Process(
        target=run_live_asr_worker,
        args=(directory, config, model_path, None, cancel, finished),
        kwargs={
            "model_factory": quiet_model_factory,
            "model_validator": fake_model_validator,
            "poll_seconds": 0.05,
            "parent_poll_seconds": 2.0,
        },
    )
    child.start()
    Path(pid_file).write_text(str(child.pid), encoding="ascii")
    time.sleep(30)


def test_orphan_worker_exits_when_parent_is_killed(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    config = LiveConfig(meeting, "a" * 32, "b" * 32, "test/base", "revision-1")
    model_path = tmp_path / "models" / "installed" / config.model_id
    model_path.mkdir(parents=True)
    pid_file = tmp_path / "child.pid"
    context = multiprocessing.get_context("spawn")
    parent = context.Process(
        target=_spawn_live_child,
        args=(str(store._meeting_dir(meeting)), config, str(model_path), str(pid_file)),
    )
    parent.start()
    child = None
    try:
        wait_until(pid_file.is_file, timeout=10)
        child = psutil.Process(int(pid_file.read_text(encoding="ascii")))
        checkpoint_path = (
            store._meeting_dir(meeting)
            / "transcripts"
            / f".live-{config.run_id}"
            / "checkpoint.sqlite3"
        )
        wait_until(checkpoint_path.is_file, timeout=10)
        meeting_lock = live_meeting_lock_path(store.root, meeting)
        model_lock = live_model_lock_path(tmp_path / "models", config.model_id)
        assert_exclusive_busy(meeting_lock)
        assert_exclusive_busy(model_lock)
        parent.terminate()
        parent.join(5)
        assert not parent.is_alive()
        assert child.is_running()
        assert_exclusive_busy(meeting_lock)
        assert_exclusive_busy(model_lock)
        child.wait(timeout=10)
        assert not child.is_running()
        assert_exclusive_available(meeting_lock)
        assert_exclusive_available(model_lock)
    finally:
        if parent.is_alive():
            parent.terminate()
            parent.join(5)
        if child is not None and child.is_running():
            child.kill()
            child.wait(timeout=5)
