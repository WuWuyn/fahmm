"""Offline Whisper adapter. The caller supplies only verified local paths."""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fahmm.models import validate_model_dir

LANGUAGES = {"vi", "en", "auto"}

# Only these constant messages may cross the bridge: backend exceptions can
# contain user paths, model metadata, or other private information.
ASR_ERROR_MESSAGES = {
    "asr_failed": "Transcription failed. Check the audio and selected model.",
    "asr_memory_low": (
        "Transcription stopped because available system memory is too low. "
        "Audio and previous transcripts were kept."
    ),
    "asr_memory_unavailable": (
        "Could not check available system memory. Transcription stopped; "
        "audio and previous transcripts were kept."
    ),
    "audio_missing": "Saved meeting audio is missing",
    "worker_crash": "ASR worker stopped unexpectedly.",
    "cuda_driver": "CUDA could not access a compatible NVIDIA GPU or driver.",
    "cuda_cublas": "CUDA could not load cuBLAS (cublas64_12.dll) or a required dependency.",
    "cuda_cudnn": "CUDA could not load cuDNN (cudnn64_9.dll) or a required dependency.",
    "cuda_runtime": "CUDA libraries are missing or incompatible. Check cuBLAS and cuDNN.",
    "cuda_compute": "This GPU does not support the selected CUDA compute type.",
    "cuda_vram": "CUDA ran out of GPU memory. Try a smaller model or free GPU memory.",
    "cuda_failed": "CUDA transcription failed. Check the GPU driver and CUDA runtime.",
    "cuda_worker_crash": (
        "ASR worker stopped unexpectedly while using CUDA. "
        "Check the GPU driver, CUDA libraries and GPU memory."
    ),
}


class ASRRuntimeError(RuntimeError):
    """An ASR failure with a stable, non-sensitive public error code."""

    def __init__(self, code: str):
        if code not in ASR_ERROR_MESSAGES:
            raise ValueError("Unknown ASR error code")
        self.code = code
        super().__init__(ASR_ERROR_MESSAGES[code])


def _cuda_error_code(exc: Exception) -> str:
    """Classify native errors without returning their potentially private text."""
    if isinstance(exc, ASRRuntimeError):
        return exc.code
    message = str(exc).casefold()
    if any(term in message for term in ("out of memory", "status_alloc_failed", "out_of_memory")):
        return "cuda_vram"
    if "driver" in message or "no cuda-capable device" in message:
        return "cuda_driver"
    if "cublas" in message and ".dll" in message:
        return "cuda_cublas"
    if "cudnn" in message and ".dll" in message:
        return "cuda_cudnn"
    if any(term in message for term in ("cublas", "cudnn", "cuda runtime", "cudart")):
        return "cuda_runtime"
    if any(term in message for term in ("compute type", "not compiled with cuda", "not supported")):
        return "cuda_compute"
    return "cuda_failed"


def _check_cuda_libraries() -> None:
    """Check loadability, not just file existence, using the native DLL search path."""
    import ctypes

    for name, code in (("cublas64_12.dll", "cuda_cublas"), ("cudnn64_9.dll", "cuda_cudnn")):
        try:
            ctypes.WinDLL(name, winmode=0)
        except OSError as exc:
            raise ASRRuntimeError(code) from exc


def _check_cuda_runtime(compute_type: str) -> None:
    """Fail before inference if the requested CUDA runtime is unavailable.

    A successful check is not proof that model inference will work. All checks
    run in the spawned ASR worker and never install or modify system libraries.
    """
    import ctranslate2

    try:
        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        raise ASRRuntimeError(_cuda_error_code(exc)) from exc
    if count < 1:
        raise ASRRuntimeError("cuda_driver")
    if sys.platform == "win32":
        _check_cuda_libraries()
    try:
        supported = ctranslate2.get_supported_compute_types("cuda")
    except Exception as exc:
        raise ASRRuntimeError(_cuda_error_code(exc)) from exc
    if compute_type not in supported:
        raise ASRRuntimeError("cuda_compute")


def _runtime_settings() -> tuple[str, str, int]:
    """Validate optional ASR tuning without changing the CPU default."""
    device = os.environ.get("FAHMM_ASR_DEVICE", "cpu").strip().lower()
    if device not in {"cpu", "cuda"}:
        raise ValueError("FAHMM_ASR_DEVICE must be cpu or cuda")
    default_compute = "int8" if device == "cpu" else "int8_float16"
    compute_type = os.environ.get("FAHMM_ASR_COMPUTE_TYPE", default_compute).strip().lower()
    if compute_type != default_compute:
        raise ValueError(f"FAHMM_ASR_COMPUTE_TYPE must be {default_compute} for {device}")
    try:
        beam_size = int(os.environ.get("FAHMM_ASR_BEAM_SIZE", "5"))
    except ValueError as exc:
        raise ValueError("FAHMM_ASR_BEAM_SIZE must be an integer from 1 to 10") from exc
    if not 1 <= beam_size <= 10:
        raise ValueError("FAHMM_ASR_BEAM_SIZE must be an integer from 1 to 10")
    return device, compute_type, beam_size


@dataclass(frozen=True)
class Segment:
    id: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class ASRInfo:
    selected_language: str
    detected_language: str | None
    duration: float


class ASRBackend(Protocol):
    def transcribe(
        self, audio_path: Path, model_path: Path, language: str = "vi", start_seconds: float = 0.0
    ) -> tuple[Iterable[Segment], ASRInfo]: ...


class WhisperASRBackend:
    def transcribe(
        self, audio_path: Path, model_path: Path, language: str = "vi", start_seconds: float = 0.0
    ) -> tuple[Iterable[Segment], ASRInfo]:
        if language not in LANGUAGES:
            raise ValueError("Choose Vietnamese, Auto Detect, or English")
        if not math.isfinite(start_seconds) or start_seconds < 0:
            raise ValueError("The transcription start time must be non-negative")
        audio_path = Path(audio_path)
        model_path = Path(model_path)
        if not audio_path.is_file():
            raise FileNotFoundError("Saved meeting audio is missing")
        validate_model_dir(model_path)
        device, compute_type, beam_size = _runtime_settings()
        if device == "cuda":
            _check_cuda_runtime(compute_type)
        # This process must never use Hub downloads, including tokenizer fallback.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio

        audio = decode_audio(str(audio_path.resolve()))
        duration = len(audio) / 16_000
        start_sample = int(start_seconds * 16_000)
        if start_sample >= len(audio):
            raise ValueError("The transcription start time must be before the end of the recording")

        try:
            model = WhisperModel(
                str(model_path.resolve()),
                device=device,
                compute_type=compute_type,
                local_files_only=True,
            )
            raw_segments, info = model.transcribe(
                audio[start_sample:],
                task="transcribe",
                language=None if language == "auto" else language,
                vad_filter=True,
                beam_size=beam_size,
            )
        except Exception as exc:
            if device == "cuda":
                raise ASRRuntimeError(_cuda_error_code(exc)) from exc
            raise
        origin = start_sample / 16_000

        def bounded_segments() -> Iterable[Segment]:
            try:
                for segment in raw_segments:
                    start = min(duration, max(origin, origin + float(segment.start)))
                    end = min(duration, max(start, origin + float(segment.end)))
                    text = segment.text.strip()
                    if start < end and text:
                        yield Segment(segment.id, start, end, text)
            except Exception as exc:
                if device == "cuda":
                    raise ASRRuntimeError(_cuda_error_code(exc)) from exc
                raise

        return bounded_segments(), ASRInfo(language, info.language, duration)
