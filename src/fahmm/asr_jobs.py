"""Parent-side ASR job lifecycle; native inference stays in a spawned process."""

from __future__ import annotations

import math
import multiprocessing
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import psutil

from fahmm.asr import ASR_ERROR_MESSAGES, LANGUAGES
from fahmm.asr_worker import run_asr_worker
from fahmm.library import MeetingLibrary
from fahmm.media import probe_audio
from fahmm.models import InstalledModel, ModelManager
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


@dataclass(frozen=True)
class JobSnapshot:
    state: str
    meeting_id: str | None
    run_id: str | None
    progress: float | None
    segment_count: int
    error: str | None
    error_code: str | None = None


Completion = Callable[[str, str, InstalledModel, str, dict, list[dict]], None]

_EMERGENCY_AVAILABLE_BYTES = 1536 * 1024 * 1024
_MEMORY_SAMPLE_SECONDS = 0.2


def _run_guarded_worker(worker_target, gate, cancel, *args) -> None:
    # A spawned process must not load the model until the first memory sample.
    gate.wait()
    if cancel.is_set():
        return
    worker_target(*args)


def _stop_worker(process) -> None:
    """Never release a worker's leases until the OS confirms it has exited."""
    if not process.is_alive():
        process.join(timeout=0)
        return
    try:
        process.terminate()
    except (OSError, ValueError):
        pass
    process.join(timeout=2)
    if process.is_alive():
        try:
            process.kill()
        except (OSError, ValueError):
            pass
    while process.is_alive():
        process.join(timeout=0.2)
    process.join(timeout=0)


class _MemoryWatchdog:
    """Stop only this job's worker if system-wide available RAM is unsafe."""

    def __init__(self, process, gate) -> None:
        self.process = process
        self.gate = gate
        self.stop_event = threading.Event()
        self.failed = threading.Event()
        self.error_code: str | None = None
        self._transition_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        with self._transition_lock:
            self.stop_event.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=2)

    def _run(self) -> None:
        first = True
        while not self.stop_event.is_set():
            try:
                available = psutil.virtual_memory().available
                code = "asr_memory_low" if available <= _EMERGENCY_AVAILABLE_BYTES else None
            except Exception:
                code = "asr_memory_unavailable"
            with self._transition_lock:
                if self.stop_event.is_set():
                    return
                if code:
                    self.error_code = code
                    self.failed.set()
                    try:
                        if self.process.is_alive():
                            self.process.terminate()
                    except (OSError, ValueError, AssertionError):
                        pass
                    return
                if first:
                    self.gate.set()
                    first = False
            if self.stop_event.wait(_MEMORY_SAMPLE_SECONDS):
                return


class ASRJobController:
    def __init__(
        self,
        store: MeetingStore,
        models: ModelManager,
        *,
        on_complete: Completion | None = None,
        worker_target=run_asr_worker,
    ) -> None:
        self.store = store
        self.library = MeetingLibrary(store)
        self.models = models
        self.on_complete = on_complete or TranscriptStore(store).save_run
        self.worker_target = worker_target
        self._lock = threading.RLock()
        self._snapshot = JobSnapshot("idle", None, None, None, 0, None)
        self._last_options: tuple[str, str, str, float] | None = None
        self._monitor_thread: threading.Thread | None = None
        self._process = None
        self._cancel_event = None

    def snapshot(self) -> JobSnapshot:
        with self._lock:
            return self._snapshot

    def _set(self, **updates) -> None:
        with self._lock:
            self._snapshot = JobSnapshot(**{**vars(self._snapshot), **updates})

    def start(
        self, meeting_id: str, model_id: str, language: str = "vi", start_seconds: float = 0.0
    ) -> str:
        if language not in LANGUAGES:
            raise ValueError("Choose Vietnamese, Auto Detect, or English")
        if (
            type(start_seconds) not in (int, float)
            or not math.isfinite(start_seconds)
            or start_seconds < 0
        ):
            raise ValueError("The transcription start time must be non-negative")
        with self._lock:
            if self._snapshot.state in ("loading", "running", "cancelling") or (
                self._monitor_thread is not None and self._monitor_thread.is_alive()
            ):
                raise RuntimeError("A transcription job is already active")
            self.store.begin_activity(meeting_id, "asr")
            model = None
            process = None
            watchdog = None
            metadata_running = False
            try:
                audio_path = self.library.audio_path(meeting_id)
                if start_seconds >= probe_audio(audio_path).seconds:
                    raise ValueError(
                        "The transcription start time must be before the end of the recording"
                    )
                model = self.models.begin_use(model_id)
                run_id = uuid.uuid4().hex
                context = multiprocessing.get_context("spawn")
                cuda_requested = os.environ.get("FAHMM_ASR_DEVICE", "cpu").strip().lower() == "cuda"
                output = context.Queue(maxsize=128)
                cancel = context.Event()
                gate = context.Event()
                process = context.Process(
                    target=_run_guarded_worker,
                    args=(
                        self.worker_target,
                        gate,
                        cancel,
                        str(audio_path),
                        str(model.path),
                        language,
                        output,
                        cancel,
                        start_seconds,
                    ),
                    daemon=True,
                )
                self.store.update_metadata(meeting_id, processing_state="running")
                metadata_running = True
                process.start()
                watchdog = _MemoryWatchdog(process, gate)
                watchdog.start()
                self._snapshot = JobSnapshot("loading", meeting_id, run_id, None, 0, None)
                self._last_options = (meeting_id, model_id, language, start_seconds)
                self._process = process
                self._cancel_event = cancel
                self._monitor_thread = threading.Thread(
                    target=self._monitor,
                    args=(
                        process,
                        output,
                        cancel,
                        meeting_id,
                        run_id,
                        model,
                        language,
                        cuda_requested,
                        watchdog,
                    ),
                    daemon=True,
                )
                self._monitor_thread.start()
                return run_id
            except Exception:
                if watchdog is not None:
                    watchdog.stop()
                if process is not None and process.is_alive():
                    _stop_worker(process)
                if model is not None:
                    self.models.end_use(model_id)
                if metadata_running:
                    self.store.update_metadata(meeting_id, processing_state="error")
                self.store.end_activity(meeting_id, "asr")
                raise

    def cancel(self) -> None:
        with self._lock:
            if self._snapshot.state not in ("loading", "running"):
                return
            self._snapshot = JobSnapshot(**{**vars(self._snapshot), "state": "cancelling"})
            self._cancel_event.set()

    def retry(self) -> str:
        if self._last_options is None:
            raise RuntimeError("There is no transcription job to retry")
        return self.start(*self._last_options)

    def wait(self, timeout: float = 10.0) -> None:
        thread = self._monitor_thread
        if thread is not None:
            thread.join(timeout)

    def _monitor(
        self, process, output, cancel, meeting_id, run_id, model, language, cuda_requested, watchdog
    ) -> None:
        info = None
        segments: list[dict] = []
        completed = False
        error = None
        error_code = None
        cancel_deadline = None
        outcome = {
            "state": "error",
            "error": ASR_ERROR_MESSAGES["asr_failed"],
            "error_code": "asr_failed",
            "progress": None,
        }
        metadata_state = "error"
        try:
            while process.is_alive() or not output.empty():
                if watchdog.failed.is_set():
                    break
                if cancel.is_set():
                    if cancel_deadline is None:
                        cancel_deadline = time.monotonic() + 2
                    elif process.is_alive() and time.monotonic() >= cancel_deadline:
                        _stop_worker(process)
                try:
                    item = output.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item["type"] == "started":
                    info = item["info"]
                    with self._lock:
                        if not cancel.is_set():
                            self._set(state="running", progress=0.0)
                elif item["type"] == "segment":
                    segments.append(item["segment"])
                    duration = (info or {}).get("duration", 0)
                    origin = (info or {}).get("start_seconds", 0)
                    remaining = duration - origin
                    progress = (
                        min(0.99, max(0.0, (item["segment"]["end"] - origin) / remaining))
                        if remaining > 0
                        else None
                    )
                    self._set(segment_count=len(segments), progress=progress)
                elif item["type"] == "completed":
                    completed = True
                elif item["type"] == "error":
                    # Worker messages are not trusted to be safe for the UI.
                    error_code = item.get("code")
                    if error_code not in ASR_ERROR_MESSAGES:
                        error_code = "asr_failed"
                    error = ASR_ERROR_MESSAGES[error_code]
            process.join(timeout=2)
            if process.is_alive():
                _stop_worker(process)
            watchdog.stop()
            if watchdog.failed.is_set():
                error_code = watchdog.error_code
                outcome = {
                    "state": "error",
                    "error": ASR_ERROR_MESSAGES[error_code],
                    "error_code": error_code,
                    "progress": None,
                }
            elif cancel.is_set():
                outcome = {"state": "cancelled", "progress": None}
                metadata_state = "cancelled"
            elif error is not None:
                outcome = {
                    "state": "error",
                    "error": error,
                    "error_code": error_code,
                    "progress": None,
                }
            elif completed and process.exitcode == 0 and info is not None:
                if self.on_complete:
                    self.on_complete(meeting_id, run_id, model, language, info, segments)
                outcome = {"state": "completed", "progress": 1.0, "segment_count": len(segments)}
                metadata_state = "completed"
            else:
                error_code = "cuda_worker_crash" if cuda_requested else "worker_crash"
                outcome = {
                    "state": "error",
                    "error": ASR_ERROR_MESSAGES[error_code],
                    "error_code": error_code,
                    "progress": None,
                }
        except Exception:
            metadata_state = "error"
            outcome = {
                "state": "error",
                "error": ASR_ERROR_MESSAGES["asr_failed"],
                "error_code": "asr_failed",
                "progress": None,
            }
        finally:
            watchdog.stop()
            _stop_worker(process)
            try:
                self.store.update_metadata(meeting_id, processing_state=metadata_state)
            except Exception:
                outcome = {
                    "state": "error",
                    "error": ASR_ERROR_MESSAGES["asr_failed"],
                    "error_code": "asr_failed",
                    "progress": None,
                }
            self.models.end_use(model.id)
            output.close()
            self.store.end_activity(meeting_id, "asr")
            self._set(**outcome)
