"""Bounded visual peaks and managed playback conversion."""

from __future__ import annotations

import os
import uuid
import wave
from pathlib import Path

import numpy as np

from fahmm.library import MeetingLibrary
from fahmm.media import iter_pcm, probe_audio
from fahmm.storage import MeetingStore


def waveform_peaks(path: Path, bins: int) -> dict:
    if type(bins) is not int or not 64 <= bins <= 2048:
        raise ValueError("Waveform resolution must be between 64 and 2048")
    seconds = probe_audio(path).seconds
    total_frames = max(1, round(seconds * 48_000))
    maxima = np.zeros(bins, dtype=np.float32)
    for chunk in iter_pcm(path):
        samples = np.frombuffer(chunk.data, dtype="<i2")
        if not len(samples):
            continue
        first = round(chunk.start_seconds * 48_000)
        indices = np.minimum(
            bins - 1, ((first + np.arange(len(samples), dtype=np.int64)) * bins // total_frames)
        )
        amplitudes = np.abs(samples.astype(np.int32)).astype(np.float32) / 32768
        np.maximum.at(maxima, indices, amplitudes)
    return {"seconds": seconds, "peaks": maxima.round(4).tolist()}


def managed_playback_wav(store: MeetingStore, library: MeetingLibrary, meeting_id: str) -> Path:
    original = library.audio_path(meeting_id)
    if original.suffix.lower() == ".wav":
        return original
    directory = store._meeting_dir(meeting_id)
    target = directory / "playback.wav"
    if target.exists():
        try:
            probe_audio(target)
            return target
        except ValueError:
            pass
    temporary = directory / f".playback-{uuid.uuid4().hex}.tmp"
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(48_000)
            for chunk in iter_pcm(original):
                output.writeframesraw(chunk.data)
        with temporary.open("r+b") as file:
            os.fsync(file.fileno())
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
