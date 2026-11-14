"""Offline Whisper adapter. The caller supplies only verified local paths."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fahmm.models import validate_model_dir

LANGUAGES = {"vi", "en", "auto"}


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
        self, audio_path: Path, model_path: Path, language: str = "vi"
    ) -> tuple[Iterable[Segment], ASRInfo]: ...


class WhisperASRBackend:
    def transcribe(
        self, audio_path: Path, model_path: Path, language: str = "vi"
    ) -> tuple[Iterable[Segment], ASRInfo]:
        if language not in LANGUAGES:
            raise ValueError("Choose Vietnamese, Auto Detect, or English")
        audio_path = Path(audio_path)
        model_path = Path(model_path)
        if not audio_path.is_file():
            raise FileNotFoundError("Saved meeting audio is missing")
        validate_model_dir(model_path)
        # This process must never use Hub downloads, including tokenizer fallback.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from faster_whisper import WhisperModel

        model = WhisperModel(
            str(model_path.resolve()), device="cpu", compute_type="int8", local_files_only=True
        )
        raw_segments, info = model.transcribe(
            str(audio_path.resolve()),
            task="transcribe",
            language=None if language == "auto" else language,
            vad_filter=False,
        )
        segments = (
            Segment(segment.id, float(segment.start), float(segment.end), segment.text.strip())
            for segment in raw_segments
        )
        return segments, ASRInfo(language, info.language, float(info.duration))
