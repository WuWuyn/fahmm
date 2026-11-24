"""Exercise kernel locks across real spawned processes, including abrupt exit."""

import multiprocessing
import threading
import time
from pathlib import Path

import pytest

from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path, live_model_lock_path


def test_live_lock_paths_are_stable_and_outside_resource_directories(tmp_path):
    resource_id = "a" * 32
    meeting = live_meeting_lock_path(tmp_path / "meetings", resource_id)
    model = live_model_lock_path(tmp_path / "models", resource_id)
    assert meeting == live_meeting_lock_path(tmp_path / "meetings", resource_id)
    assert meeting.parent == (tmp_path / "meetings" / ".live-locks").resolve()
    assert model.parent == (tmp_path / "models" / ".live-locks").resolve()
    assert meeting != model
    with pytest.raises(ValueError):
        live_meeting_lock_path(tmp_path, "../invalid")


def _hold_lock(path, shared, ready, release, finished):
    lock = SharedFileLock(Path(path), shared=shared)
    try:
        lock.acquire(timeout=5)
        ready.set()
        release.wait(20)
    finally:
        lock.release()
        finished.set()


def _parent_with_independent_worker(path, parent_ready, worker_ready, worker_release, worker_done):
    lock = SharedFileLock(Path(path), shared=True)
    lock.acquire(timeout=5)
    worker = multiprocessing.get_context("spawn").Process(
        target=_hold_lock, args=(path, True, worker_ready, worker_release, worker_done)
    )
    worker.start()
    parent_ready.set()
    # The test terminates this parent to simulate an application crash.
    time.sleep(20)
    lock.release()
    worker.join(timeout=5)


def test_shared_processes_block_exclusive_until_the_last_release(tmp_path):
    path = tmp_path / "model.lock"
    original = b"Do not replace this content"
    path.write_bytes(original)
    context = multiprocessing.get_context("spawn")
    ready1, ready2, release1, release2, done1, done2 = (context.Event() for _ in range(6))
    first = context.Process(target=_hold_lock, args=(str(path), True, ready1, release1, done1))
    second = context.Process(target=_hold_lock, args=(str(path), True, ready2, release2, done2))
    first.start()
    second.start()
    try:
        assert ready1.wait(10) and ready2.wait(10)
        with SharedFileLock(path, shared=True), pytest.raises(TimeoutError):
            SharedFileLock(path, shared=False).acquire(timeout=0.1)
        first.terminate()
        first.join(timeout=5)
        assert not first.is_alive()
        with pytest.raises(TimeoutError):
            SharedFileLock(path, shared=False).acquire(timeout=0.1)
        release2.set()
        second.join(timeout=10)
        assert second.exitcode == 0 and done2.is_set()
        with SharedFileLock(path, shared=False):
            pass
        assert path.read_bytes() == original
    finally:
        # Do not touch an Event whose waiter was terminated: Windows can leave
        # its synchronization primitive in a non-recoverable state.
        if first.is_alive():
            first.terminate()
            first.join(timeout=5)
        if second.is_alive():
            release2.set()
            second.join(timeout=5)
            if second.is_alive():
                second.terminate()
                second.join(timeout=5)


def test_worker_lock_survives_parent_crash_until_worker_releases(tmp_path):
    path = tmp_path / "meeting.lock"
    context = multiprocessing.get_context("spawn")
    parent_ready, worker_ready, worker_release, worker_done = (context.Event() for _ in range(4))
    parent = context.Process(
        target=_parent_with_independent_worker,
        args=(str(path), parent_ready, worker_ready, worker_release, worker_done),
    )
    parent.start()
    try:
        assert parent_ready.wait(10) and worker_ready.wait(10)
        parent.terminate()
        parent.join(timeout=5)
        assert not parent.is_alive()
        with pytest.raises(TimeoutError):
            SharedFileLock(path, shared=False).acquire(timeout=0.1)
        worker_release.set()
        assert worker_done.wait(10)
        with SharedFileLock(path, shared=False):
            pass
    finally:
        worker_release.set()
        if parent.is_alive():
            parent.terminate()
            parent.join(timeout=5)
        worker_done.wait(5)


def test_exclusive_blocks_shared_and_wait_can_be_cancelled(tmp_path):
    path = tmp_path / "resource.lock"
    exclusive = SharedFileLock(path, shared=False)
    exclusive.acquire()
    cancelled = threading.Event()
    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    try:
        with pytest.raises(TimeoutError):
            SharedFileLock(path, shared=True).acquire(timeout=0)
        started = time.monotonic()
        with pytest.raises(InterruptedError):
            SharedFileLock(path, shared=True).acquire(timeout=5, cancel=cancelled)
        assert time.monotonic() - started < 2
    finally:
        timer.cancel()
        exclusive.release()
    with SharedFileLock(path, shared=True):
        pass


def test_lock_handle_can_be_released_on_another_thread(tmp_path):
    path = tmp_path / "cross-thread.lock"
    lock = SharedFileLock(path, shared=True)
    lock.acquire()
    failures = []

    def release():
        try:
            lock.release()
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=release)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive() and not failures
    with SharedFileLock(path, shared=False):
        pass


def test_cancel_before_acquire_and_exception_release_leave_file_unchanged(tmp_path):
    path = tmp_path / "data.lock"
    expected = b"unchanged"
    path.write_bytes(expected)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InterruptedError):
        SharedFileLock(path, shared=True).acquire(timeout=0, cancel=cancelled)
    with pytest.raises(RuntimeError, match="body failure"), SharedFileLock(path, shared=True):
        raise RuntimeError("body failure")
    with SharedFileLock(path, shared=False):
        pass
    assert path.read_bytes() == expected


def test_acquired_handle_rejects_second_acquire(tmp_path):
    lock = SharedFileLock(tmp_path / "once.lock", shared=True)
    lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="already acquired"):
            lock.acquire(timeout=0)
    finally:
        lock.release()
    lock.release()  # Cleanup remains idempotent.
