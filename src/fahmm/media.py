"""Local audio probing and import; never modifies the selected source."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import av

from fahmm.storage import MeetingStore

SUPPORTED_EXTENSIONS = frozenset({".wav", ".mp3", ".m4a", ".flac"})
COPY_BLOCK = 8 * 1024 * 1024


@dataclass(frozen=True)
class AudioInfo:
    seconds: float
    sample_rate: int
    channels: int


def probe_audio(path: Path) -> AudioInfo:
    """Check playable head/tail and duration without decoding a long file in the UI."""
    try:
        with av.open(str(path), mode="r") as container:
            streams = container.streams.audio
            if not streams:
                raise ValueError("The file contains no audio stream")
            stream = streams[0]
            first = next(container.decode(stream), None)
            if first is None or first.samples <= 0 or first.sample_rate <= 0:
                raise ValueError("The file contains no decodable audio")
            duration = (
                float(stream.duration * stream.time_base)
                if stream.duration is not None and stream.time_base is not None
                else float(container.duration / av.time_base) if container.duration else 0.0
            )
            if duration > 1 and stream.time_base is not None:
                container.seek(int((duration - 0.5) / float(stream.time_base)), stream=stream)
                last_end = 0.0
                for frame in container.decode(stream):
                    if frame.time is not None:
                        last_end = max(last_end, float(frame.time) + frame.samples / frame.sample_rate)
                if last_end < duration - 1:
                    raise ValueError("The audio file is incomplete or truncated")
            return AudioInfo(
                duration or first.samples / first.sample_rate,
                first.sample_rate,
                len(first.layout.channels),
            )
    except (OSError, av.FFmpegError) as exc:
        raise ValueError(f"The audio file cannot be decoded: {exc}") from exc


@dataclass(frozen=True)
class PCMChunk:
    start_seconds: float
    data: bytes


def iter_pcm(path: Path, start_seconds: float = 0.0, rate: int = 48_000):
    """Yield mono PCM16 from a local file, beginning at a source timestamp."""
    if start_seconds < 0:
        raise ValueError("Playback time cannot be negative")
    with av.open(str(path), mode="r") as container:
        streams = container.streams.audio
        if not streams:
            raise ValueError("The file contains no audio stream")
        stream = streams[0]
        if start_seconds:
            offset = int(start_seconds / float(stream.time_base))
            container.seek(offset, stream=stream, backward=True)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
        next_time = 0.0
        for frame in container.decode(stream):
            frame_time = float(frame.time) if frame.time is not None else next_time
            cursor = frame_time
            for converted in resampler.resample(frame):
                data = converted.to_ndarray().tobytes()
                samples = converted.samples
                if cursor + samples / rate > start_seconds:
                    skipped = max(0, min(samples, int((start_seconds - cursor) * rate)))
                    if skipped < samples:
                        yield PCMChunk(cursor + skipped / rate, data[skipped * 2 :])
                cursor += samples / rate
            next_time = frame_time + frame.samples / frame.sample_rate
        for converted in resampler.resample(None):
            if next_time + converted.samples / rate > start_seconds:
                skipped = max(0, int((start_seconds - next_time) * rate))
                if skipped < converted.samples:
                    yield PCMChunk(
                        next_time + skipped / rate,
                        converted.to_ndarray().tobytes()[skipped * 2 :],
                    )
            next_time += converted.samples / rate


def import_audio(store: MeetingStore, source: Path) -> str:
    """Copy, verify, then publish a new restricted meeting in the local store."""
    source = Path(source)
    extension = source.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported audio format. Choose WAV, MP3, M4A, or FLAC.")
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("The selected audio file is missing or empty")
    store.root.mkdir(parents=True, exist_ok=True)
    size = source.stat().st_size
    if shutil.disk_usage(store.root).free < size + COPY_BLOCK:
        raise OSError("Not enough free disk space to import this recording")
    meeting_id = uuid.uuid4().hex
    staging = store.root / f".import-{meeting_id}"
    target = store._meeting_dir(meeting_id)
    audio_name = f"audio{extension}"
    staging.mkdir(exist_ok=False)
    store.begin_import(meeting_id)
    published = False
    try:
        copied = staging / audio_name
        with source.open("rb") as input_file, copied.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=COPY_BLOCK)
            output_file.flush()
            os.fsync(output_file.fileno())
        probe_audio(copied)
        os.replace(staging, target)
        published = True
        store._write_metadata(
            meeting_id,
            {
                "schema_version": 2,
                "id": meeting_id,
                "created_at": datetime.now(UTC).isoformat(),
                "state": "completed",
                "devices": {},
                "name": source.stem or "Untitled meeting",
                "source_kind": "imported",
                "audio_file": audio_name,
                "privacy_mode": "restricted",
                "processing_state": "not_started",
            },
        )
        return meeting_id
    except Exception:
        directory = target if published else staging
        (directory / audio_name).unlink(missing_ok=True)
        directory.rmdir()
        raise
    finally:
        store.end_import(meeting_id)
