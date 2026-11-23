"""Offline Whisper adapter. The caller supplies only verified local paths."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fahmm.models import validate_model_dir

LANGUAGES = {"vi", "en", "auto"}


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
        origin = start_sample / 16_000

        def bounded_segments() -> Iterable[Segment]:
            for segment in raw_segments:
                start = min(duration, max(origin, origin + float(segment.start)))
                end = min(duration, max(start, origin + float(segment.end)))
                text = segment.text.strip()
                if start < end and text:
                    yield Segment(segment.id, start, end, text)

        return bounded_segments(), ASRInfo(language, info.language, duration)
