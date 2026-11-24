"""Crash-tolerant local WAV storage. No filesystem work happens at import time."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from fahmm.local_locks import exclusive_file_lock

SAMPLE_RATE = 48_000
CHUNK_RE = re.compile(r"^(\d{12})-[0-9a-f]{8}\.wav$")
SOURCES = ("system", "microphone")
PRIVACY_MODES = ("restricted", "cloud_permitted")


def normalized_privacy_mode(value: object) -> str:
    return value if value in PRIVACY_MODES else "restricted"


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
        self._metadata_lock = threading.RLock()
        self._cloud_sends: dict[str, int] = {}
        self._activities: dict[str, dict[str, int]] = {}
        self._deleting: set[str] = set()
        self._imports: set[str] = set()

    def _meeting_dir(self, meeting_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", meeting_id):
            raise ValueError("Invalid meeting ID")
        return self.root / meeting_id

    @contextmanager
    def input_guard(
        self, meeting_id: str, *, cancel: threading.Event | None = None, timeout: float = 10.0
    ):
        """Serialize updates to inputs shared by transcript and minutes jobs."""
        directory = self._meeting_dir(meeting_id)
        if not directory.is_dir():
            raise FileNotFoundError("Meeting does not exist")
        with exclusive_file_lock(directory / ".inputs.lock", cancel=cancel, timeout=timeout):
            yield

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
                "schema_version": 2,
                "id": meeting_id,
                "created_at": datetime.now(UTC).isoformat(),
                "state": "recording",
                "devices": devices,
                "name": "Untitled meeting",
                "source_kind": "recorded",
                "audio_file": "recording.wav",
                "privacy_mode": "restricted",
                "processing_state": "not_started",
            },
        )
        return meeting_id

    def metadata(self, meeting_id: str) -> dict:
        with self._metadata_lock:
            with (self._meeting_dir(meeting_id) / "metadata.json").open(encoding="utf-8") as file:
                data = json.load(file)
            if data.get("id") != meeting_id or data.get("schema_version") not in (1, 2):
                raise ValueError("Incompatible meeting metadata")
            if data["schema_version"] == 1:
                data = {
                    **data,
                    "schema_version": 2,
                    "name": "Untitled meeting",
                    "source_kind": "recorded",
                    "audio_file": "recording.wav",
                    "privacy_mode": "restricted",
                    "processing_state": "not_started",
                }
            data["privacy_mode"] = normalized_privacy_mode(data.get("privacy_mode"))
            return data

    def _write_metadata(self, meeting_id: str, data: dict) -> None:
        with self._metadata_lock:
            directory = self._meeting_dir(meeting_id)
            target = directory / "metadata.json"
            temporary = directory / f".metadata-{uuid.uuid4().hex}.tmp"
            backup = directory / "metadata.v1.json"
            if target.exists() and not backup.exists():
                with target.open(encoding="utf-8") as file:
                    previous = json.load(file)
                if previous.get("schema_version") == 1:
                    backup_tmp = directory / f".metadata-v1-{uuid.uuid4().hex}.tmp"
                    try:
                        shutil.copyfile(target, backup_tmp)
                        with backup_tmp.open("r+b") as file:
                            os.fsync(file.fileno())
                        os.replace(backup_tmp, backup)
                    finally:
                        backup_tmp.unlink(missing_ok=True)
            try:
                with temporary.open("w", encoding="utf-8") as file:
                    json.dump(data, file, ensure_ascii=False, indent=2)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def update_metadata(self, meeting_id: str, **changes: object) -> dict:
        with self.input_guard(meeting_id), self._metadata_lock:
            if meeting_id in self._deleting:
                raise RuntimeError("This meeting is being deleted")
            data = self.metadata(meeting_id)
            data.update(changes)
            self._write_metadata(meeting_id, data)
            return data

    def set_state(self, meeting_id: str, state: str) -> None:
        self.update_metadata(meeting_id, state=state)

    def privacy_mode(self, meeting_id: str) -> str:
        return self.metadata(meeting_id)["privacy_mode"]

    def set_privacy_mode(self, meeting_id: str, mode: str) -> None:
        if mode not in PRIVACY_MODES:
            raise ValueError("Unknown meeting privacy mode")
        with self.input_guard(meeting_id), self._metadata_lock:
            if self._cloud_sends.get(meeting_id, 0):
                raise RuntimeError("Wait for the current provider request to finish")
            self.update_metadata(meeting_id, privacy_mode=mode)

    def begin_activity(self, meeting_id: str, kind: str) -> None:
        if not kind:
            raise ValueError("Meeting activity kind is required")
        with self._metadata_lock:
            if meeting_id in self._deleting:
                raise RuntimeError("This meeting is being deleted")
            self.metadata(meeting_id)
            kinds = self._activities.setdefault(meeting_id, {})
            kinds[kind] = kinds.get(kind, 0) + 1

    def end_activity(self, meeting_id: str, kind: str) -> None:
        with self._metadata_lock:
            kinds = self._activities.get(meeting_id)
            if not kinds or not kinds.get(kind):
                raise RuntimeError("Meeting activity was not started")
            if kinds[kind] == 1:
                del kinds[kind]
            else:
                kinds[kind] -= 1
            if not kinds:
                del self._activities[meeting_id]

    @contextmanager
    def activity(self, meeting_id: str, kind: str):
        self.begin_activity(meeting_id, kind)
        try:
            yield
        finally:
            self.end_activity(meeting_id, kind)

    def active_activities(self, meeting_id: str) -> tuple[str, ...]:
        with self._metadata_lock:
            return tuple(sorted(self._activities.get(meeting_id, {})))

    def begin_deletion(self, meeting_id: str) -> None:
        with self._metadata_lock:
            self.metadata(meeting_id)
            if meeting_id in self._deleting:
                raise RuntimeError("This meeting is already being deleted")
            kinds = self.active_activities(meeting_id)
            if kinds:
                raise RuntimeError(f"Wait for active meeting work to finish: {', '.join(kinds)}")
            self._deleting.add(meeting_id)

    def end_deletion(self, meeting_id: str) -> None:
        with self._metadata_lock:
            self._deleting.discard(meeting_id)

    def begin_tombstone_cleanup(self, meeting_id: str) -> None:
        with self._metadata_lock:
            canonical = self._meeting_dir(meeting_id)
            if canonical.exists():
                raise RuntimeError("A live meeting with this ID still exists")
            if (
                meeting_id in self._deleting
                or self._activities.get(meeting_id)
                or meeting_id in self._imports
            ):
                raise RuntimeError("Wait for active meeting work to finish")
            self._deleting.add(meeting_id)

    def begin_import(self, meeting_id: str) -> None:
        self._meeting_dir(meeting_id)
        with self._metadata_lock:
            if meeting_id in self._deleting:
                raise RuntimeError("This import is being cleaned up")
            if meeting_id in self._imports:
                raise RuntimeError("This import is already active")
            self._imports.add(meeting_id)

    def end_import(self, meeting_id: str) -> None:
        with self._metadata_lock:
            self._imports.discard(meeting_id)

    def active_imports(self) -> tuple[str, ...]:
        with self._metadata_lock:
            return tuple(sorted(self._imports))

    def begin_cloud_send(self, meeting_id: str) -> None:
        with self._metadata_lock:
            if self.privacy_mode(meeting_id) != "cloud_permitted":
                raise PermissionError("This meeting is Internal/Restricted")
            self.begin_activity(meeting_id, "provider_send")
            self._cloud_sends[meeting_id] = self._cloud_sends.get(meeting_id, 0) + 1

    def end_cloud_send(self, meeting_id: str) -> None:
        with self._metadata_lock:
            count = self._cloud_sends.get(meeting_id, 0)
            if count <= 1:
                self._cloud_sends.pop(meeting_id, None)
            else:
                self._cloud_sends[meeting_id] = count - 1
            self.end_activity(meeting_id, "provider_send")

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
                if (
                    data["source_kind"] == "recorded"
                    and data["state"] != "completed"
                    and any(chunks.values())
                ):
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
                next_chunk = {source: 0 for source in SOURCES}
                active: dict[str, list[Chunk]] = {source: [] for source in SOURCES}
                for start in range(0, last_frame, SAMPLE_RATE):
                    end = min(start + SAMPLE_RATE, last_frame)
                    stereo = np.zeros((end - start, 2), dtype="<i2")
                    for channel, source in enumerate(SOURCES):
                        # scan_chunks() orders by offset and then filename. Keep
                        # that order for active chunks so later overlaps still
                        # overwrite earlier samples exactly as before.
                        active[source] = [
                            chunk
                            for chunk in active[source]
                            if chunk.start_frame + chunk.frames > start
                        ]
                        source_chunks = chunks[source]
                        while (
                            next_chunk[source] < len(source_chunks)
                            and source_chunks[next_chunk[source]].start_frame < end
                        ):
                            chunk = source_chunks[next_chunk[source]]
                            next_chunk[source] += 1
                            if chunk.start_frame + chunk.frames > start:
                                active[source].append(chunk)
                        for chunk in active[source]:
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
            self.update_metadata(
                meeting_id, state="completed", recording=str(target), skipped_chunks=list(skipped)
            )
            return RecoveryResult(target, skipped)
        except Exception:
            self.set_state(meeting_id, "error")
            raise
        finally:
            temporary.unlink(missing_ok=True)
