"""RAM safety decisions use deterministic samples and fake owned processes."""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import benchmark_asr, measure_70min_resources
from scripts.benchmark_memory import MIB, MemoryGuard, MemoryPolicy, MemoryWatchdog


def test_preflight_emergency_sustained_and_recovery():
    policy = MemoryPolicy(start_mib=5000, sustained_mib=2000, emergency_mib=1500, grace_seconds=5)
    guard = MemoryGuard(policy)
    assert guard.preflight(4999 * MIB) == "insufficient_start_memory"
    assert guard.preflight(5000 * MIB) is None
    assert guard.preflight(None) == "memory_sample_unavailable"
    assert guard.observe(1500 * MIB, 0) == "emergency_low_memory"
    assert guard.observe(1900 * MIB, 0) is None
    assert guard.observe(1900 * MIB, 4.99) is None
    assert guard.observe(2100 * MIB, 5) is None  # recovery resets the sustained timer
    assert guard.observe(1900 * MIB, 6) is None
    assert guard.observe(1900 * MIB, 11) == "sustained_low_memory"
    assert guard.observe(None, 12) == "memory_sample_unavailable"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_mib": 0},
        {"start_mib": 1000, "sustained_mib": 2000},
        {"sustained_mib": 1000, "emergency_mib": 1500},
        {"grace_seconds": float("nan")},
        {"sample_seconds": 0},
    ],
)
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        MemoryPolicy(**kwargs)


def test_watchdog_independently_stops_on_one_emergency_sample():
    values = iter([6000 * MIB, 76 * MIB])
    stopped = threading.Event()
    reasons = []

    def abort(reason):
        reasons.append(reason)
        stopped.set()

    watchdog = MemoryWatchdog(MemoryPolicy(sample_seconds=0.01), lambda: next(values), abort)
    watchdog.start()
    try:
        assert stopped.wait(2)
        assert reasons == ["emergency_low_memory"]
        assert watchdog.minimum_available == 76 * MIB
    finally:
        watchdog.stop()


def test_asr_does_not_spawn_when_start_headroom_is_insufficient(monkeypatch):
    monkeypatch.setattr(benchmark_asr, "_available_memory", lambda: 4000 * MIB)
    monkeypatch.setattr(
        benchmark_asr.multiprocessing,
        "get_context",
        lambda *_args: pytest.fail("worker must not be created"),
    )
    result = benchmark_asr.run_case(
        Path("audio"),
        Path("model"),
        None,
        "vi",
        "cpu",
        1,
        max_seconds=30,
        min_free_mib=2048,
        grace_seconds=5,
        gpu_metrics=False,
    )
    assert result["state"] == "stopped" and result["reason"] == "insufficient_start_memory"


@pytest.mark.parametrize("gpu_metrics", [False, True])
def test_asr_emergency_watchdog_terminates_only_owned_worker(monkeypatch, gpu_metrics):
    gpu_entered = threading.Event()
    worker_stopped = threading.Event()
    count = 0

    def memory():
        nonlocal count
        count += 1
        if count <= 2:
            return 6000 * MIB
        if gpu_metrics:
            assert gpu_entered.wait(1)
        return 76 * MIB

    def slow_gpu():
        gpu_entered.set()
        worker_stopped.wait(2)
        return 0

    monkeypatch.setattr(benchmark_asr, "_available_memory", memory)
    monkeypatch.setattr(benchmark_asr, "_gpu_total_mib", slow_gpu)
    gate = threading.Event()

    class FakeQueue:
        def __init__(self):
            self.closed = threading.Event()

        def get(self):
            self.closed.wait(2)
            raise EOFError

        def cancel_join_thread(self):
            return None

        def close(self):
            self.closed.set()

    class Worker:
        pid = 1234

        def __init__(self):
            self.alive = False
            self.terminated = False

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True
            self.alive = False
            worker_stopped.set()

        def kill(self):
            self.alive = False

        def join(self, timeout=None):
            return None

    worker = Worker()
    unrelated = Worker()

    class Context:
        def Queue(self, **_kwargs):
            return FakeQueue()

        def Event(self):
            return gate

        def Process(self, **_kwargs):
            return worker

    observed = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=123),
        cpu_times=lambda: SimpleNamespace(user=0, system=0),
    )
    monkeypatch.setattr(benchmark_asr.multiprocessing, "get_context", lambda *_args: Context())
    monkeypatch.setattr(benchmark_asr.psutil, "Process", lambda pid: observed)
    result = benchmark_asr.run_case(
        Path("audio"),
        Path("model"),
        None,
        "vi",
        "cpu",
        1,
        max_seconds=30,
        min_free_mib=2048,
        grace_seconds=5,
        gpu_metrics=gpu_metrics,
        sample_seconds=0.01,
    )
    assert gate.is_set()
    assert result["reason"] == "emergency_low_memory"
    assert result["minimum_system_available_mib"] == 76
    assert worker.terminated and not unrelated.terminated


class FakeProcess:
    def __init__(self, children=()):
        self.children_list = list(children)
        self.alive = True
        self.killed = False

    def is_running(self):
        return self.alive

    def children(self, recursive=False):
        assert recursive
        return self.children_list

    def kill(self):
        self.killed = True
        self.alive = False


def test_measure_watchdog_stops_only_owned_sidecar_tree(tmp_path, monkeypatch):
    child = FakeProcess()
    sidecar = FakeProcess([child])
    unrelated_ollama = FakeProcess()
    samples = iter([6000 * MIB, 76 * MIB])
    monkeypatch.setattr(measure_70min_resources, "_available_memory", lambda: next(samples))
    monkeypatch.setattr(measure_70min_resources.psutil, "Process", lambda _pid: sidecar)
    monkeypatch.setattr(measure_70min_resources.psutil, "cpu_percent", lambda *_args: 0)
    monkeypatch.setattr(
        measure_70min_resources,
        "MEMORY_POLICY",
        MemoryPolicy(sample_seconds=0.01),
    )
    monitor = measure_70min_resources.Monitor(100, 200, tmp_path / "samples.jsonl")
    try:
        assert monitor.watchdog._thread.join(timeout=2) is None
        assert monitor.memory_abort_reason == "emergency_low_memory"
        assert sidecar.killed and child.killed
        assert not unrelated_ollama.killed
    finally:
        monitor.stop()


def test_stale_sidecar_identity_is_not_signalled():
    child = FakeProcess()
    stale = FakeProcess([child])
    stale.alive = False
    measure_70min_resources._stop_owned_sidecar(stale)
    assert not stale.killed and not child.killed


def test_known_worker_is_stopped_even_if_owned_sidecar_has_exited():
    child = FakeProcess()
    stale = FakeProcess()
    stale.alive = False
    unrelated = FakeProcess()
    measure_70min_resources._stop_owned_sidecar(stale, [child])
    assert not stale.killed and child.killed and not unrelated.killed
