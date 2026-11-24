import queue
import threading
from types import SimpleNamespace

import pytest
from test_asr_jobs import prepared_job, quick_worker

from fahmm import asr_jobs
from fahmm.asr_jobs import ASRJobController, JobSnapshot


def test_cancel_before_gate_prevents_worker_start():
    gate = threading.Event()
    cancel = threading.Event()
    called = []
    cancel.set()
    gate.set()
    asr_jobs._run_guarded_worker(lambda: called.append(True), gate, cancel)
    assert not called


def test_retry_is_blocked_until_metadata_and_cleanup_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(
        asr_jobs.psutil, "virtual_memory", lambda: SimpleNamespace(available=3 * 1024**3)
    )
    job, meeting, model_id, _ = prepared_job(tmp_path, quick_worker)
    entered, release = threading.Event(), threading.Event()
    original = job.store.update_metadata

    def block_metadata(*args, **kwargs):
        if kwargs.get("processing_state") == "completed":
            entered.set()
            assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(job.store, "update_metadata", block_metadata)
    job.start(meeting, model_id)
    try:
        assert entered.wait(10)
        assert job.snapshot().state in ("loading", "running")
        with pytest.raises(RuntimeError, match="already active"):
            job.start(meeting, model_id)
    finally:
        release.set()
        job.wait(10)
    assert job.snapshot().state == "completed"
    job.start(meeting, model_id)
    job.wait(10)
    assert job.snapshot().state == "completed"


def test_leases_remain_held_until_worker_exit_is_confirmed():
    exited = threading.Event()
    calls = []

    class StuckProcess:
        exitcode = -9

        def is_alive(self):
            return not exited.is_set()

        def terminate(self):
            calls.append("terminate")

        def kill(self):
            calls.append("kill")

        def join(self, timeout=None):
            exited.wait(0.01)

    class Output(queue.Queue):
        def close(self):
            calls.append("close")

    class Store:
        def update_metadata(self, *args, **kwargs):
            calls.append("metadata")

        def end_activity(self, *args):
            calls.append("activity_release")

    class Models:
        def end_use(self, *args):
            calls.append("model_release")

    failed = threading.Event()
    failed.set()
    watchdog = SimpleNamespace(failed=failed, error_code="asr_memory_low", stop=lambda: None)
    job = ASRJobController(Store(), Models())
    job._snapshot = JobSnapshot("loading", "meeting", "run", None, 0, None)
    monitor = threading.Thread(
        target=job._monitor,
        args=(
            StuckProcess(),
            Output(),
            threading.Event(),
            "meeting",
            "run",
            SimpleNamespace(id="model"),
            "vi",
            False,
            watchdog,
        ),
        daemon=True,
    )
    monitor.start()
    try:
        deadline = threading.Event()
        for _ in range(100):
            if "kill" in calls:
                break
            deadline.wait(0.01)
        assert "kill" in calls
        assert "model_release" not in calls and "activity_release" not in calls
        assert job.snapshot().state == "loading"
    finally:
        exited.set()
        monitor.join(5)
    assert not monitor.is_alive()
    assert "model_release" in calls and "activity_release" in calls
    assert job.snapshot().error_code == "asr_memory_low"


def test_watchdog_ignores_memory_sample_completed_after_stop(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def delayed_reading():
        entered.set()
        assert release.wait(10)
        return SimpleNamespace(available=1)

    monkeypatch.setattr(asr_jobs.psutil, "virtual_memory", delayed_reading)
    process = SimpleNamespace(is_alive=lambda: True, terminate=lambda: calls.append("terminate"))
    gate = threading.Event()
    watchdog = asr_jobs._MemoryWatchdog(process, gate)
    watchdog.start()
    assert entered.wait(5)
    watchdog.stop()
    release.set()
    watchdog.thread.join(5)
    assert not watchdog.thread.is_alive()
    assert not calls and not watchdog.failed.is_set() and not gate.is_set()
