"""Parent-side lifecycle for experimental live ASR workers.

This controller is not yet wired into the desktop bridge or UI.  It never
selects or overwrites the meeting's active transcript.
"""

from __future__ import annotations

import multiprocessing
import os
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path

from fahmm.asr import ASR_ERROR_MESSAGES, _runtime_settings
from fahmm.controller import SessionController
from fahmm.live_asr import (
    LIVE_ERRORS,
    LiveASRError,
    LiveCheckpoint,
    LiveConfig,
    LiveLease,
    run_live_asr_worker,
)
from fahmm.models import ModelManager
from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path, live_model_lock_path
from fahmm.storage import SAMPLE_RATE, MeetingStore

_ACTIVE = {"starting", "running", "cancelling"}


def _live_cpu_threads() -> int:
    value = os.environ.get("FAHMM_LIVE_CPU_THREADS")
    if value is None:
        return max(1, min(4, (os.cpu_count() or 2) // 2))
    try:
        threads = int(value)
    except ValueError as exc:
        raise ValueError("FAHMM_LIVE_CPU_THREADS must be an integer from 1 to 4") from exc
    if not 1 <= threads <= 4:
        raise ValueError("FAHMM_LIVE_CPU_THREADS must be an integer from 1 to 4")
    return threads


@dataclass(frozen=True)
class LiveJobSnapshot:
    state: str = "idle"
    meeting_id: str | None = None
    run_id: str | None = None
    cursor_seconds: float = 0.0
    segment_count: int = 0
    provisional_count: int = 0
    review_windows: int = 0
    error_code: str | None = None
    capture_status: str | None = None
    backlog_seconds: float | None = None


class LiveASRJobs:
    """Own one process, its resources, and its checkpoint monitor."""

    def __init__(
        self,
        store: MeetingStore,
        models: ModelManager,
        recorder: SessionController,
        *,
        worker_target=run_live_asr_worker,
        cancel_timeout: float = 2.0,
        poll_interval: float = 0.1,
        queue_size: int = 32,
    ) -> None:
        if cancel_timeout <= 0 or poll_interval <= 0 or queue_size < 1:
            raise ValueError("Invalid live worker lifecycle settings")
        if recorder.store is not store:
            raise ValueError("Recorder and live transcription must share a meeting store")
        self.store = store
        self.models = models
        self.recorder = recorder
        self.worker_target = worker_target
        self.cancel_timeout = cancel_timeout
        self.poll_interval = poll_interval
        self.queue_size = queue_size
        self._lock = threading.RLock()
        self._snapshot = LiveJobSnapshot()
        self._cancel = None
        self._process = None
        self._monitor_thread: threading.Thread | None = None

    def snapshot(self) -> LiveJobSnapshot:
        with self._lock:
            return self._snapshot

    def _set(self, **fields) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, **fields)

    def start(self, meeting_id: str, model_id: str, language: str = "vi") -> str:
        with self._lock:
            return self._start(meeting_id, model_id, language, None)

    def resume(self, meeting_id: str, run_id: str) -> str:
        with self._lock:
            return self._start(meeting_id, None, None, run_id)

    def _start(
        self, meeting_id: str, model_id: str | None, language: str | None, run_id: str | None
    ) -> str:
        if self._snapshot.state in _ACTIVE or (
            self._monitor_thread is not None and self._monitor_thread.is_alive()
        ):
            raise RuntimeError("A live transcription is already active")
        resources = ExitStack()
        model = None
        process = None
        output = None
        try:
            meeting_lock = SharedFileLock(
                live_meeting_lock_path(self.store.root, meeting_id), shared=True
            )
            meeting_lock.acquire(timeout=0)
            resources.callback(meeting_lock.release)
            directory = self.store._meeting_dir(meeting_id)
            if run_id is not None:
                config = LiveCheckpoint.load_config(directory, run_id)
                selected_model = config.model_id
            else:
                if model_id is None or language is None:
                    raise ValueError("A model and language are required")
                selected_model = model_id
            model_lock = SharedFileLock(
                live_model_lock_path(self.models.root, selected_model), shared=True
            )
            model_lock.acquire(timeout=0)
            resources.callback(model_lock.release)
            capture = self.recorder.capture_status(meeting_id)
            if capture not in {"writing", "closed"}:
                raise RuntimeError("Recover the recording before starting live transcription")
            self.store.begin_activity(meeting_id, "live_asr")
            resources.callback(self.store.end_activity, meeting_id, "live_asr")
            if run_id is not None:
                if LiveCheckpoint.load_config(directory, run_id) != config:
                    raise ValueError("The live checkpoint changed while starting")
                checkpoint = LiveCheckpoint(directory, config, create=False)
                try:
                    if checkpoint.get("state") in {"completed", "needs_review"}:
                        raise RuntimeError("This live run has already finished processing")
                finally:
                    checkpoint.close()
                model = self.models.begin_use(config.model_id)
                resources.callback(self.models.end_use, model.id)
                if (model.repository, model.revision) != (
                    config.model_repository,
                    config.model_revision,
                ):
                    raise ValueError("The installed model does not match the live checkpoint")
            else:
                model = self.models.begin_use(model_id)
                resources.callback(self.models.end_use, model.id)
                device, compute_type, beam_size = _runtime_settings()
                config = LiveConfig(
                    meeting_id,
                    uuid.uuid4().hex,
                    model.id,
                    model.repository,
                    model.revision,
                    language,
                    device,
                    compute_type,
                    beam_size,
                    cpu_threads=_live_cpu_threads(),
                )
                config.validate()
            context = multiprocessing.get_context("spawn")
            output = context.Queue(maxsize=self.queue_size)
            cancel, finished = context.Event(), context.Event()
            if capture == "closed":
                finished.set()
            process = context.Process(
                target=self.worker_target,
                args=(str(directory), config, str(model.path), output, cancel, finished),
                daemon=True,
            )
            process.start()
            self._snapshot = LiveJobSnapshot(
                state="starting",
                meeting_id=meeting_id,
                run_id=config.run_id,
                capture_status=capture,
            )
            self._cancel = cancel
            self._process = process
            monitor = threading.Thread(
                target=self._monitor,
                args=(process, output, cancel, finished, directory, config, resources),
                daemon=True,
            )
            self._monitor_thread = monitor
            monitor.start()
            return config.run_id
        except BaseException:
            if process is not None and process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join()
            if output is not None:
                output.cancel_join_thread()
                output.close()
            resources.close()
            self._snapshot = LiveJobSnapshot()
            self._cancel = None
            self._process = None
            raise

    def cancel(self, meeting_id: str | None = None, run_id: str | None = None) -> bool:
        with self._lock:
            if (meeting_id is not None and self._snapshot.meeting_id != meeting_id) or (
                run_id is not None and self._snapshot.run_id != run_id
            ):
                return False
            if self._snapshot.state == "cancelling":
                return True
            if self._snapshot.state not in {"starting", "running"}:
                return False
            self._snapshot = replace(self._snapshot, state="cancelling")
            self._cancel.set()
            return True

    def wait(self, timeout: float = 10.0) -> None:
        thread = self._monitor_thread
        if thread is not None:
            thread.join(timeout)

    @staticmethod
    def _read_checkpoint(directory: Path, config: LiveConfig) -> LiveCheckpoint | None:
        try:
            return LiveCheckpoint(directory, config, create=False)
        except (OSError, sqlite3.Error, ValueError, LiveASRError):
            return None

    def _monitor(
        self,
        process,
        output,
        cancel,
        finished,
        directory: Path,
        config: LiveConfig,
        resources: ExitStack,
    ) -> None:
        checkpoint = None
        cancel_deadline = None
        reason = None
        last_available = None
        worker_error = None
        try:
            while process.is_alive():
                capture = self.recorder.capture_status(config.meeting_id)
                if capture == "closed":
                    finished.set()
                elif capture in {"failed", "unknown"}:
                    reason = "live_capture_failed"
                    cancel.set()
                if cancel.is_set() and cancel_deadline is None:
                    cancel_deadline = time.monotonic() + self.cancel_timeout
                    self._set(state="cancelling")
                if cancel_deadline is not None and time.monotonic() >= cancel_deadline:
                    process.terminate()
                    process.join(timeout=1)
                    if process.is_alive():
                        process.kill()
                    cancel_deadline = time.monotonic() + self.cancel_timeout
                try:
                    item = output.get(timeout=self.poll_interval)
                    if item.get("type") == "progress":
                        last_available = item.get("available")
                    elif item.get("type") == "error" and item.get("code") in (
                        LIVE_ERRORS.keys() | ASR_ERROR_MESSAGES.keys()
                    ):
                        worker_error = item["code"]
                except queue.Empty:
                    pass
                if checkpoint is None:
                    checkpoint = self._read_checkpoint(directory, config)
                if checkpoint is not None:
                    try:
                        saved = checkpoint.snapshot()
                        backlog = (
                            max(0.0, last_available / SAMPLE_RATE - saved["cursor_seconds"])
                            if isinstance(last_available, int)
                            else None
                        )
                        self._set(
                            state="cancelling" if cancel.is_set() else "running",
                            capture_status=capture,
                            backlog_seconds=backlog,
                            cursor_seconds=saved["cursor_seconds"],
                            segment_count=saved["segment_count"],
                            provisional_count=saved["provisional_count"],
                            review_windows=saved["review_windows"],
                        )
                    except (OSError, sqlite3.Error, ValueError):
                        pass
            process.join()
            while True:
                try:
                    item = output.get_nowait()
                except queue.Empty:
                    break
                if item.get("type") == "error" and item.get("code") in (
                    LIVE_ERRORS.keys() | ASR_ERROR_MESSAGES.keys()
                ):
                    worker_error = item["code"]
            if checkpoint is None:
                checkpoint = self._read_checkpoint(directory, config)
            state, error = "error", reason or worker_error or "live_worker_crash"
            if checkpoint is None and reason is None and cancel.is_set():
                state, error = "cancelled", None
            if checkpoint is not None:
                with LiveLease(directory):
                    saved = checkpoint.snapshot()
                    if reason is not None:
                        checkpoint.set_state("error", reason)
                    elif cancel.is_set() and saved["state"] != "error":
                        checkpoint.set_state("cancelled")
                    elif (
                        process.exitcode != 0
                        and saved["state"] != "error"
                        or saved["state"] not in {"completed", "needs_review", "cancelled", "error"}
                    ):
                        checkpoint.set_state("error", "live_worker_crash")
                    saved = checkpoint.snapshot()
                    if saved["state"] == "completed" and (
                        saved["provisional_count"] or saved["review_windows"]
                    ):
                        checkpoint.set_state("needs_review")
                        saved = checkpoint.snapshot()
                state, error = saved["state"], saved["error_code"]
                self._set(
                    cursor_seconds=saved["cursor_seconds"],
                    segment_count=saved["segment_count"],
                    provisional_count=saved["provisional_count"],
                    review_windows=saved["review_windows"],
                )
            self._set(
                state=state,
                error_code=error,
                capture_status=self.recorder.capture_status(config.meeting_id),
            )
        except Exception:
            self._set(state="error", error_code="live_worker_crash")
        finally:
            # Do not unlock the model or meeting while a native worker is alive.
            while process.is_alive():
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
            try:
                if checkpoint is not None:
                    checkpoint.close()
                output.cancel_join_thread()
                output.close()
            finally:
                resources.close()
