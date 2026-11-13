"""Crash-tolerant local WAV storage. No filesystem work happens at import time."""

from __future__ import annotations

import json
import os
import re
import uuid
import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48_000
CHUNK_RE = re.compile(r"^(\d{12})-[0-9a-f]{8}\.wav$")
SOURCES = ("system", "microphone")


@dataclass(frozen=True)
class Chunk:
    path: Path
    start_frame: int
    frames: int


@dataclass(frozen=True)
class RecoveryResult:
    path: Path
    skipped_chunks: tuple[str, ...]


class MeetingStore:
    def __init__(self, root: Path | None = None) -> None:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.root = Path(root) if root is not None else base / "fahmm" / "meetings"

    def _meeting_dir(self, meeting_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", meeting_id):
            raise ValueError("Invalid meeting ID")
        return self.root / meeting_id

    def create(self, devices: dict[str, str]) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        while True:
            meeting_id = uuid.uuid4().hex
            directory = self._meeting_dir(meeting_id)
            try:
                directory.mkdir(exist_ok=False)
                break
            except FileExistsError:
                continue
        for source in SOURCES:
            (directory / source).mkdir()
        self._write_metadata(
            meeting_id,
            {
                "schema_version": 1,
                "id": meeting_id,
                "created_at": datetime.now(UTC).isoformat(),
                "state": "recording",
                "devices": devices,
            },
        )
        return meeting_id

    def metadata(self, meeting_id: str) -> dict:
        with (self._meeting_dir(meeting_id) / "metadata.json").open(encoding="utf-8") as file:
            data = json.load(file)
        if data.get("schema_version") != 1 or data.get("id") != meeting_id:
            raise ValueError("Incompatible meeting metadata")
        return data

    def _write_metadata(self, meeting_id: str, data: dict) -> None:
        directory = self._meeting_dir(meeting_id)
        target = directory / "metadata.json"
        temporary = directory / f".metadata-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def set_state(self, meeting_id: str, state: str) -> None:
        data = self.metadata(meeting_id)
        data["state"] = state
        self._write_metadata(meeting_id, data)

    def write_chunk(
        self, meeting_id: str, source: str, start_frame: int, samples: np.ndarray
    ) -> Path:
        if source not in SOURCES or start_frame < 0:
            raise ValueError("Invalid audio source or offset")
        mono = np.asarray(samples, dtype=np.float32)
        if mono.ndim != 1 or not len(mono) or not np.isfinite(mono).all():
            raise ValueError("Invalid audio chunk")
        pcm = np.rint(np.clip(mono, -1, 1) * 32767).astype("<i2")
        directory = self._meeting_dir(meeting_id) / source
        target = directory / f"{start_frame:012d}-{uuid.uuid4().hex[:8]}.wav"
        temporary = directory / f".{target.name}.tmp"
        try:
            with wave.open(str(temporary), "wb") as file:
                file.setnchannels(1)
                file.setsampwidth(2)
                file.setframerate(SAMPLE_RATE)
                file.writeframes(pcm.tobytes())
            with temporary.open("r+b") as file:
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def scan_chunks(self, meeting_id: str) -> tuple[dict[str, list[Chunk]], tuple[str, ...]]:
        directory = self._meeting_dir(meeting_id)
        found: dict[str, list[Chunk]] = {source: [] for source in SOURCES}
        skipped: list[str] = []
        for source in SOURCES:
            for path in (directory / source).glob("*.wav"):
                match = CHUNK_RE.fullmatch(path.name)
                if not match:
                    skipped.append(str(path))
                    continue
                try:
                    with wave.open(str(path), "rb") as file:
                        if (file.getnchannels(), file.getsampwidth(), file.getframerate()) != (
                            1,
                            2,
                            SAMPLE_RATE,
                        ) or file.getnframes() == 0:
                            raise ValueError("Invalid WAV format")
                        frames = file.getnframes()
                        if len(file.readframes(frames)) != frames * 2:
                            raise ValueError("Truncated WAV file")
                    found[source].append(Chunk(path, int(match.group(1)), frames))
                except (OSError, EOFError, ValueError, wave.Error):
                    skipped.append(str(path))
            found[source].sort(key=lambda item: (item.start_frame, item.path.name))
        return found, tuple(skipped)

    def incomplete(self) -> list[dict]:
        if not self.root.exists():
            return []
        result = []
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                data = self.metadata(directory.name)
                chunks, _ = self.scan_chunks(directory.name)
                if data["state"] != "completed" and any(chunks.values()):
                    result.append(data)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def finalize(self, meeting_id: str) -> RecoveryResult:
        data = self.metadata(meeting_id)
        if data["state"] == "completed":
            return RecoveryResult(self._meeting_dir(meeting_id) / "recording.wav", ())
        chunks, skipped = self.scan_chunks(meeting_id)
        if not any(chunks.values()):
            raise ValueError("No valid audio is available for recovery")
        last_frame = max(
            chunk.start_frame + chunk.frames
            for source_chunks in chunks.values()
            for chunk in source_chunks
        )
        directory = self._meeting_dir(meeting_id)
        target = directory / "recording.wav"
        temporary = directory / f".recording-{uuid.uuid4().hex}.tmp"
        self.set_state(meeting_id, "finalizing")
        try:
            with wave.open(str(temporary), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(SAMPLE_RATE)
                for start in range(0, last_frame, SAMPLE_RATE):
                    end = min(start + SAMPLE_RATE, last_frame)
                    stereo = np.zeros((end - start, 2), dtype="<i2")
                    for channel, source in enumerate(SOURCES):
                        for chunk in chunks[source]:
                            overlap_start = max(start, chunk.start_frame)
                            overlap_end = min(end, chunk.start_frame + chunk.frames)
                            if overlap_end <= overlap_start:
                                continue
                            with wave.open(str(chunk.path), "rb") as file:
                                file.setpos(overlap_start - chunk.start_frame)
                                raw = file.readframes(overlap_end - overlap_start)
                            stereo[overlap_start - start : overlap_end - start, channel] = (
                                np.frombuffer(raw, dtype="<i2")
                            )
                    output.writeframes(stereo.tobytes())
            with temporary.open("r+b") as file:
                os.fsync(file.fileno())
            os.replace(temporary, target)
            data = self.metadata(meeting_id)
            data["state"] = "completed"
            data["recording"] = str(target)
            data["skipped_chunks"] = list(skipped)
            self._write_metadata(meeting_id, data)
            return RecoveryResult(target, skipped)
        except Exception:
            self.set_state(meeting_id, "error")
            raise
        finally:
            temporary.unlink(missing_ok=True)
