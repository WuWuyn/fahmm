"""Parent-side ASR job lifecycle; native inference stays in a spawned process."""

from __future__ import annotations

import math
import multiprocessing
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fahmm.asr import LANGUAGES
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


Completion = Callable[[str, str, InstalledModel, str, dict, list[dict]], None]


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
            if self._snapshot.state in ("loading", "running", "cancelling"):
                raise RuntimeError("A transcription job is already active")
            self.store.begin_activity(meeting_id, "asr")
            model = None
            process = None
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
                output = context.Queue(maxsize=128)
                cancel = context.Event()
                process = context.Process(
                    target=self.worker_target,
                    args=(
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
                self._snapshot = JobSnapshot("loading", meeting_id, run_id, None, 0, None)
                self._last_options = (meeting_id, model_id, language, start_seconds)
                self._process = process
                self._cancel_event = cancel
                self._monitor_thread = threading.Thread(
                    target=self._monitor,
                    args=(process, output, cancel, meeting_id, run_id, model, language),
                    daemon=True,
                )
                self._monitor_thread.start()
                return run_id
            except Exception:
                if process is not None and process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
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

    def _monitor(self, process, output, cancel, meeting_id, run_id, model, language) -> None:
        info = None
        segments: list[dict] = []
        completed = False
        error = None
        cancel_deadline = None
        try:
            while process.is_alive() or not output.empty():
                if cancel.is_set():
                    if cancel_deadline is None:
                        cancel_deadline = time.monotonic() + 2
                    elif process.is_alive() and time.monotonic() >= cancel_deadline:
                        process.terminate()
                        process.join(timeout=2)
                try:
                    item = output.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item["type"] == "started":
                    info = item["info"]
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
                    error = item["message"]
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            if cancel.is_set():
                self._set(state="cancelled", progress=None)
                self.store.update_metadata(meeting_id, processing_state="cancelled")
            elif error is not None:
                self._set(state="error", error=error, progress=None)
                self.store.update_metadata(meeting_id, processing_state="error")
            elif completed and process.exitcode == 0 and info is not None:
                if self.on_complete:
                    self.on_complete(meeting_id, run_id, model, language, info, segments)
                self._set(state="completed", progress=1.0, segment_count=len(segments))
                self.store.update_metadata(meeting_id, processing_state="completed")
            else:
                self._set(state="error", error="ASR worker stopped unexpectedly", progress=None)
                self.store.update_metadata(meeting_id, processing_state="error")
        except Exception as exc:
            self._set(state="error", error=str(exc), progress=None)
            self.store.update_metadata(meeting_id, processing_state="error")
        finally:
            self.models.end_use(model.id)
            output.close()
            self.store.end_activity(meeting_id, "asr")
