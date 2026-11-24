"""Spawn-safe process entry point for local ASR."""

from __future__ import annotations

from dataclasses import asdict
from multiprocessing.synchronize import Event as MpEvent
from pathlib import Path

from fahmm.asr import ASR_ERROR_MESSAGES, ASRBackend, ASRRuntimeError, WhisperASRBackend


def _send(output, message: dict, cancel: MpEvent) -> bool:
    import queue

    while not cancel.is_set():
        try:
            output.put(message, timeout=0.2)
            return True
        except queue.Full:
            continue
    return False


def run_asr_worker(
    audio_path: str,
    model_path: str,
    language: str,
    output,
    cancel: MpEvent,
    start_seconds: float = 0.0,
    backend: ASRBackend | None = None,
) -> None:
    """Emit small status/segment messages; never write or upload meeting data."""
    try:
        worker = backend or WhisperASRBackend()
        segments, info = worker.transcribe(
            Path(audio_path), Path(model_path), language, start_seconds
        )
        if not _send(
            output,
            {"type": "started", "info": {**asdict(info), "start_seconds": start_seconds}},
            cancel,
        ):
            return
        for segment in segments:
            if not _send(output, {"type": "segment", "segment": asdict(segment)}, cancel):
                return
        _send(output, {"type": "completed"}, cancel)
    except Exception as exc:
        if isinstance(exc, ASRRuntimeError):
            code = exc.code
        elif isinstance(exc, FileNotFoundError) and str(exc) == "Saved meeting audio is missing":
            code = "audio_missing"
        else:
            code = "asr_failed"
        _send(output, {"type": "error", "code": code, "message": ASR_ERROR_MESSAGES[code]}, cancel)
