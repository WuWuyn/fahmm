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

# A misbehaving device must not accumulate unbounded samples that appear to be
# ahead of the recording clock while capture remains active.
MAX_BUFFER_FRAMES = SAMPLE_RATE * 4


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
    levels: dict[str, float]


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
        self._levels = {source: 0.0 for source in SOURCES}
        self._started_at = 0.0
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._stopped_at: float | None = None
        # Capture reads can finish after a pause or stop. Keep the first end
        # boundary for each recording epoch, even across a fast resume.
        self._capture_epoch = 0
        self._capture_cutoffs: dict[int, int] = {}
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._gate = threading.Event()
        self._ready: dict[str, threading.Event] = {}
        self._worker: threading.Thread | None = None
        self._capture_threads: dict[str, tuple[threading.Thread, ...]] = {}
        self._capture_failures: set[str] = set()

    def capture_status(self, meeting_id: str) -> str:
        """Report whether both capture writers have exited for this meeting.

        An interrupted meeting from an earlier process is unknown until it has
        been recovered; a recorder error is not proof that its writers stopped.
        """
        data = self.store.metadata(meeting_id)
        if data["source_kind"] != "recorded":
            return "unknown"
        with self._lock:
            threads = self._capture_threads.get(meeting_id)
            failed = meeting_id in self._capture_failures
            if failed:
                return "failed"
            if threads is not None:
                if any(thread.ident is None or thread.is_alive() for thread in threads):
                    return "writing"
                return "closed"
            if self._meeting_id == meeting_id and self._state in (
                State.STARTING,
                State.RECORDING,
                State.PAUSED,
                State.FINALIZING,
            ):
                return "writing"
        if (
            data["state"] == "completed"
            and data.get("audio_file") == "recording.wav"
            and (self.store._meeting_dir(meeting_id) / "recording.wav").is_file()
        ):
            return "closed"
        return "unknown"

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                self._state,
                self._elapsed(),
                self._meeting_id,
                self._recording,
                self._error,
                self._skipped,
                dict(self._levels),
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
            if any(
                thread.is_alive()
                for threads in self._capture_threads.values()
                for thread in threads
            ):
                raise RuntimeError("Wait for previous capture devices to close")
            available = self.capture.list_devices()
            for source, device_id in (("system", system_id), ("microphone", microphone_id)):
                if not any(item.id == device_id for item in available[source]):
                    raise ValueError(f"The selected {source} device is no longer available")
            self._meeting_id = self.store.create({"system": system_id, "microphone": microphone_id})
            self.store.begin_activity(self._meeting_id, "recording")
            self._recording = None
            self._error = None
            self._skipped = ()
            self._levels = {source: 0.0 for source in SOURCES}
            self._state = State.STARTING
            self._started_at = 0.0
            self._paused_at = None
            self._paused_total = 0.0
            self._stopped_at = None
            self._capture_epoch = 0
            self._capture_cutoffs = {}
            self._stop = threading.Event()
            self._resume = threading.Event()
            self._resume.set()
            self._gate = threading.Event()
            self._ready = {source: threading.Event() for source in SOURCES}
            self._worker = threading.Thread(
                target=self._run_session_guarded, args=(system_id, microphone_id), daemon=True
            )
            try:
                self._worker.start()
            except Exception:
                self.store.end_activity(self._meeting_id, "recording")
                raise
            return self._meeting_id

    def pause(self) -> None:
        with self._lock:
            if self._state != State.RECORDING:
                raise RuntimeError("The session is not recording")
            self._paused_at = time.monotonic()
            self._close_capture_epoch()
            self._state = State.PAUSED
            self._levels = {source: 0.0 for source in SOURCES}
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
            stopped_at = time.monotonic()
            if self._paused_at is not None:
                self._paused_total += stopped_at - self._paused_at
                self._paused_at = None
            self._state = State.FINALIZING
            self._levels = {source: 0.0 for source in SOURCES}
            self._stopped_at = stopped_at
            self._close_capture_epoch()
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
            if any(
                thread.is_alive()
                for threads in self._capture_threads.values()
                for thread in threads
            ):
                raise RuntimeError("Wait for previous capture devices to close")
            self.store.begin_activity(meeting_id, "recovery")
            self._state = State.FINALIZING
            self._meeting_id = meeting_id
            self._started_at = 0.0
            self._stopped_at = None
            self._recording = None
            self._error = None
            self._skipped = ()
            self._levels = {source: 0.0 for source in SOURCES}
        try:
            threading.Thread(target=self._recover_guarded, args=(meeting_id,), daemon=True).start()
        except Exception:
            self.store.end_activity(meeting_id, "recovery")
            raise

    def _recover_guarded(self, meeting_id: str) -> None:
        try:
            self._finish(meeting_id)
        finally:
            self.store.end_activity(meeting_id, "recovery")

    def wait(self, timeout: float = 10.0) -> None:
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _close_capture_epoch(self) -> None:
        """Record an immutable sample cutoff while holding the state lock."""
        self._capture_cutoffs[self._capture_epoch] = int(self._elapsed() * SAMPLE_RATE)
        self._capture_epoch += 1

    def _fail(self, source: str, exc: Exception) -> None:
        label = "system audio" if source == "system" else "microphone"
        with self._lock:
            if self._meeting_id is not None:
                self._capture_failures.add(self._meeting_id)
            self._error = f"{label} error: {exc}"
            self._state = State.ERROR
            self._levels = {source: 0.0 for source in SOURCES}
            self._stopped_at = time.monotonic()
            self._close_capture_epoch()
            self._stop.set()
            self._resume.set()
            self._gate.set()
            self._ready[source].set()

    def _run_session_guarded(self, system_id: str, microphone_id: str) -> None:
        meeting_id = self._meeting_id
        try:
            self._run_session(system_id, microphone_id)
        except Exception as exc:
            self._fail("system", exc)
            self.store.set_state(meeting_id, "error")
        finally:
            self.store.end_activity(meeting_id, "recording")

    def _run_session(self, system_id: str, microphone_id: str) -> None:
        meeting_id = self._meeting_id
        threads = [
            threading.Thread(
                target=self._capture_source, args=(meeting_id, source, device_id), daemon=True
            )
            for source, device_id in (("system", system_id), ("microphone", microphone_id))
        ]
        with self._lock:
            self._capture_threads[meeting_id] = tuple(threads)
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

    def _flush_capture_buffer(
        self,
        meeting_id: str,
        source: str,
        start_frame: int | None,
        epoch: int | None,
        blocks: list[np.ndarray],
        *,
        final: bool,
    ) -> bool:
        """Flush only samples within an already observed recording boundary.

        A fast device can hand back samples ahead of our wall-clock timeline.
        While active, retain that buffer until the clock catches up. Once an
        epoch has ended (or on an error), trim its tail to the known cutoff.
        """
        if start_frame is None or epoch is None or not blocks:
            return True
        count = sum(map(len, blocks))
        with self._lock:
            current = int(self._elapsed() * SAMPLE_RATE)
            cutoff = self._capture_cutoffs.get(epoch)
            if cutoff is None and not final and start_frame + count > current:
                return False
            allowed = max(0, min(count, (cutoff if cutoff is not None else current) - start_frame))
        if allowed:
            self.store.write_chunk(
                meeting_id, source, start_frame, np.concatenate(blocks)[:allowed]
            )
        return True

    def _capture_source(self, meeting_id: str, source: str, device_id: str) -> None:
        first = True
        try:
            while not self._stop.is_set():
                if not self._resume.wait(0.1):
                    continue
                blocks: list[np.ndarray] = []
                start_frame: int | None = None
                buffer_epoch: int | None = None
                with self._lock:
                    if self._stop.is_set() or not self._resume.is_set():
                        continue
                    stream_epoch = self._capture_epoch
                try:
                    with self.capture.open(source, device_id) as stream:
                        if first:
                            self._ready[source].set()
                            first = False
                            self._gate.wait()
                        while not self._stop.is_set() and self._resume.is_set():
                            with self._lock:
                                if self._stop.is_set() or not self._resume.is_set():
                                    break
                                offset = int(self._elapsed() * SAMPLE_RATE)
                                epoch = self._capture_epoch
                                if stream_epoch != epoch:
                                    break
                                if buffer_epoch is not None and buffer_epoch != epoch:
                                    break
                            data = stream.read(2048)
                            with self._lock:
                                interrupted = (
                                    epoch != self._capture_epoch
                                    or self._stop.is_set()
                                    or not self._resume.is_set()
                                )
                                cutoff = self._capture_cutoffs.get(epoch)
                                if interrupted:
                                    # Chunk samples are written contiguously. Account
                                    # for both the read's wall-clock offset and their
                                    # assigned position when trimming at the boundary.
                                    assigned = (
                                        start_frame + sum(map(len, blocks))
                                        if start_frame is not None
                                        else offset
                                    )
                                    keep = (
                                        max(0, cutoff - max(offset, assigned))
                                        if cutoff is not None
                                        else 0
                                    )
                                    data = data[:keep]
                                if len(data):
                                    if start_frame is None:
                                        start_frame = offset
                                        buffer_epoch = epoch
                                    blocks.append(data)
                                buffered = sum(map(len, blocks))
                            if not len(data):
                                if interrupted:
                                    break
                                continue
                            level = float(np.sqrt(np.mean(np.square(data, dtype=np.float64))))
                            with self._lock:
                                if epoch == self._capture_epoch and self._state == State.RECORDING:
                                    self._levels[source] = min(1.0, level * 6)
                            if buffered >= SAMPLE_RATE * 2:
                                if self._flush_capture_buffer(
                                    meeting_id,
                                    source,
                                    start_frame,
                                    buffer_epoch,
                                    blocks,
                                    final=False,
                                ):
                                    blocks = []
                                    start_frame = None
                                    buffer_epoch = None
                                elif buffered > MAX_BUFFER_FRAMES:
                                    raise RuntimeError("Audio capture exceeded the recording clock")
                            if interrupted:
                                break
                finally:
                    if blocks and start_frame is not None:
                        self._flush_capture_buffer(
                            meeting_id, source, start_frame, buffer_epoch, blocks, final=True
                        )
        except Exception as exc:
            self._fail(source, exc)

    def _finish(self, meeting_id: str) -> None:
        try:
            result = self.store.finalize(meeting_id)
            with self._lock:
                self._capture_failures.discard(meeting_id)
                self._recording = result.path
                self._skipped = result.skipped_chunks
                self._state = State.COMPLETED
                self._levels = {source: 0.0 for source in SOURCES}
        except Exception as exc:
            with self._lock:
                self._error = f"Could not create the playback file: {exc}"
                self._state = State.ERROR
                self._levels = {source: 0.0 for source in SOURCES}
