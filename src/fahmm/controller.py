"""Recording state machine, independent of Qt and the concrete capture backend."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from fahmm.audio import AudioCapture
from fahmm.storage import SAMPLE_RATE, SOURCES, MeetingStore


class State(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass(frozen=True)
class Snapshot:
    state: State
    seconds: float
    meeting_id: str | None
    recording: Path | None
    error: str | None
    skipped_chunks: tuple[str, ...]


class SessionController:
    def __init__(self, capture: AudioCapture, store: MeetingStore) -> None:
        self.capture = capture
        self.store = store
        self._lock = threading.RLock()
        self._state = State.IDLE
        self._meeting_id: str | None = None
        self._recording: Path | None = None
        self._error: str | None = None
        self._skipped: tuple[str, ...] = ()
        self._started_at = 0.0
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._stopped_at: float | None = None
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._gate = threading.Event()
        self._ready: dict[str, threading.Event] = {}
        self._worker: threading.Thread | None = None

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                self._state,
                self._elapsed(),
                self._meeting_id,
                self._recording,
                self._error,
                self._skipped,
            )

    def _elapsed(self) -> float:
        if not self._started_at:
            return 0.0
        end = self._paused_at or self._stopped_at or time.monotonic()
        return max(0.0, end - self._started_at - self._paused_total)

    def start(self, system_id: str, microphone_id: str) -> str:
        with self._lock:
            if self._state in (State.STARTING, State.RECORDING, State.PAUSED, State.FINALIZING):
                raise RuntimeError("A recording session is already active")
            available = self.capture.list_devices()
            for source, device_id in (("system", system_id), ("microphone", microphone_id)):
                if not any(item.id == device_id for item in available[source]):
                    raise ValueError(f"The selected {source} device is no longer available")
            self._meeting_id = self.store.create({"system": system_id, "microphone": microphone_id})
            self._recording = None
            self._error = None
            self._skipped = ()
            self._state = State.STARTING
            self._started_at = 0.0
            self._paused_at = None
            self._paused_total = 0.0
            self._stopped_at = None
            self._stop = threading.Event()
            self._resume = threading.Event()
            self._resume.set()
            self._gate = threading.Event()
            self._ready = {source: threading.Event() for source in SOURCES}
            self._worker = threading.Thread(
                target=self._run_session, args=(system_id, microphone_id), daemon=True
            )
            self._worker.start()
            return self._meeting_id

    def pause(self) -> None:
        with self._lock:
            if self._state != State.RECORDING:
                raise RuntimeError("The session is not recording")
            self._paused_at = time.monotonic()
            self._state = State.PAUSED
            self._resume.clear()

    def resume(self) -> None:
        with self._lock:
            if self._state != State.PAUSED:
                raise RuntimeError("The session is not paused")
            self._paused_total += time.monotonic() - self._paused_at
            self._paused_at = None
            self._state = State.RECORDING
            self._resume.set()

    def stop(self) -> None:
        with self._lock:
            if self._state not in (State.STARTING, State.RECORDING, State.PAUSED):
                raise RuntimeError("There is no recording to stop")
            starting = self._state == State.STARTING
            if self._paused_at is not None:
                self._paused_total += time.monotonic() - self._paused_at
                self._paused_at = None
            self._state = State.FINALIZING
            self._stopped_at = time.monotonic()
            self._stop.set()
            self._resume.set()
            self._gate.set()
            if starting:
                for ready in self._ready.values():
                    ready.set()

    def recover(self, meeting_id: str) -> None:
        with self._lock:
            if self._state in (State.STARTING, State.RECORDING, State.PAUSED, State.FINALIZING):
                raise RuntimeError("Another session is being processed")
            self._state = State.FINALIZING
            self._meeting_id = meeting_id
            self._started_at = 0.0
            self._stopped_at = None
            self._recording = None
            self._error = None
            self._skipped = ()
        threading.Thread(target=self._finish, args=(meeting_id,), daemon=True).start()

    def wait(self, timeout: float = 10.0) -> None:
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _fail(self, source: str, exc: Exception) -> None:
        label = "system audio" if source == "system" else "microphone"
        with self._lock:
            self._error = f"{label} error: {exc}"
            self._state = State.ERROR
            self._stopped_at = time.monotonic()
            self._stop.set()
            self._resume.set()
            self._gate.set()
            self._ready[source].set()

    def _run_session(self, system_id: str, microphone_id: str) -> None:
        meeting_id = self._meeting_id
        threads = [
            threading.Thread(
                target=self._capture_source, args=(meeting_id, source, device_id), daemon=True
            )
            for source, device_id in (("system", system_id), ("microphone", microphone_id))
        ]
        for thread in threads:
            thread.start()
        for source in SOURCES:
            if not self._ready[source].wait(10):
                self._fail(source, TimeoutError("The device did not respond"))
        with self._lock:
            if not self._stop.is_set():
                self._started_at = time.monotonic()
                self._state = State.RECORDING
                self._gate.set()
        self._stop.wait()
        self._resume.set()
        self._gate.set()
        for thread in threads:
            thread.join(10)
        if any(thread.is_alive() for thread in threads):
            self._fail("system", TimeoutError("Could not close the audio device"))
        with self._lock:
            failed = self._state == State.ERROR
        if failed:
            self.store.set_state(meeting_id, "error")
        else:
            self._finish(meeting_id)

    def _capture_source(self, meeting_id: str, source: str, device_id: str) -> None:
        first = True
        try:
            while not self._stop.is_set():
                if not self._resume.wait(0.1):
                    continue
                blocks: list[np.ndarray] = []
                start_frame: int | None = None
                try:
                    with self.capture.open(source, device_id) as stream:
                        if first:
                            self._ready[source].set()
                            first = False
                            self._gate.wait()
                        while not self._stop.is_set() and self._resume.is_set():
                            with self._lock:
                                offset = int(self._elapsed() * SAMPLE_RATE)
                            data = stream.read(2048)
                            if self._stop.is_set() or not self._resume.is_set():
                                break
                            if not len(data):
                                continue
                            if start_frame is None:
                                start_frame = offset
                            blocks.append(data)
                            if sum(map(len, blocks)) >= SAMPLE_RATE * 2:
                                self.store.write_chunk(
                                    meeting_id, source, start_frame, np.concatenate(blocks)
                                )
                                blocks = []
                                start_frame = None
                finally:
                    if blocks and start_frame is not None:
                        self.store.write_chunk(
                            meeting_id, source, start_frame, np.concatenate(blocks)
                        )
        except Exception as exc:
            self._fail(source, exc)

    def _finish(self, meeting_id: str) -> None:
        try:
            result = self.store.finalize(meeting_id)
            with self._lock:
                self._recording = result.path
                self._skipped = result.skipped_chunks
                self._state = State.COMPLETED
        except Exception as exc:
            with self._lock:
                self._error = f"Could not create the playback file: {exc}"
                self._state = State.ERROR
