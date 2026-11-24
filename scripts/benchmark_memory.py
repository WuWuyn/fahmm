"""Conservative sampled RAM limits for local benchmark subprocesses."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

MIB = 1024**2


@dataclass(frozen=True)
class MemoryPolicy:
    """Thresholds refer to OS-reported available RAM, not process memory."""

    start_mib: int = 5120
    sustained_mib: int = 2048
    emergency_mib: int = 1536
    grace_seconds: float = 5.0
    sample_seconds: float = 0.2

    def __post_init__(self) -> None:
        values = (self.start_mib, self.sustained_mib, self.emergency_mib)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("RAM thresholds must be positive integer MiB")
        if not self.start_mib >= self.sustained_mib >= self.emergency_mib:
            raise ValueError(
                "Start RAM must be at least sustained RAM, which must be at least emergency RAM"
            )
        for value in (self.grace_seconds, self.sample_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("RAM guard timings must be finite and positive")

    def as_dict(self) -> dict:
        return {
            "source": "psutil.virtual_memory().available (system-wide available RAM)",
            "start_free_mib": self.start_mib,
            "sustained_free_mib": self.sustained_mib,
            "emergency_free_mib": self.emergency_mib,
            "grace_seconds": self.grace_seconds,
            "sample_seconds": self.sample_seconds,
            "sampling_limitation": "A sudden allocation between samples can still exhaust RAM",
        }


class MemoryGuard:
    def __init__(self, policy: MemoryPolicy) -> None:
        self.policy = policy
        self.low_since: float | None = None

    def preflight(self, available: int | None) -> str | None:
        if type(available) is not int or available < 0:
            return "memory_sample_unavailable"
        if available < self.policy.start_mib * MIB:
            return "insufficient_start_memory"
        return None

    def observe(self, available: int | None, now: float) -> str | None:
        if type(available) is not int or available < 0:
            return "memory_sample_unavailable"
        if available <= self.policy.emergency_mib * MIB:
            return "emergency_low_memory"
        if available < self.policy.sustained_mib * MIB:
            if self.low_since is None:
                self.low_since = now
            if now - self.low_since >= self.policy.grace_seconds:
                return "sustained_low_memory"
        else:
            self.low_since = None
        return None


class MemoryWatchdog:
    """Sample independently of blocking inference, process or GPU telemetry."""

    def __init__(
        self,
        policy: MemoryPolicy,
        read_available: Callable[[], int | None],
        on_abort: Callable[[str], None],
        *,
        initial_available: int | None = None,
    ) -> None:
        self.policy = policy
        self.read_available = read_available
        self.on_abort = on_abort
        self.guard = MemoryGuard(policy)
        self.reason: str | None = None
        self.minimum_available = initial_available
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(5):
            self.reason = "memory_sample_unavailable"
            self.on_abort(self.reason)
            raise RuntimeError("RAM watchdog did not start")

    def _run(self) -> None:
        first_sample = True
        while not self._stop.is_set():
            try:
                available = self.read_available()
            except Exception:
                available = None
            if type(available) is int and available >= 0:
                self.minimum_available = (
                    available
                    if self.minimum_available is None
                    else min(self.minimum_available, available)
                )
            reason = (
                self.guard.preflight(available)
                if first_sample
                else self.guard.observe(available, time.monotonic())
            )
            first_sample = False
            if reason:
                self.reason = reason
                self._ready.set()
                self.on_abort(reason)
                return
            self._ready.set()
            if self._stop.wait(self.policy.sample_seconds):
                return

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
