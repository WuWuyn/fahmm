"""Versioned local transcription results with immutable ASR output."""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore


def _write_json(path: Path, data: object) -> None:
    temporary = path.parent / f".{path.name}-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class TranscriptStore:
    def __init__(self, meetings: MeetingStore) -> None:
        self.meetings = meetings

    def _run_dir(self, meeting_id: str, run_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid transcription run ID")
        return self.meetings._meeting_dir(meeting_id) / "transcripts" / run_id

    def save_run(
        self,
        meeting_id: str,
        run_id: str,
        model: InstalledModel,
        language: str,
        info: dict,
        segments: list[dict],
    ) -> None:
        target = self._run_dir(meeting_id, run_id)
        if target.exists():
            raise FileExistsError("This transcription run already exists")
        ids = [segment["id"] for segment in segments]
        duration = info.get("duration")
        start_seconds = info.get("start_seconds", 0.0)
        if (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration <= 0
            or type(start_seconds) not in (int, float)
            or not math.isfinite(start_seconds)
            or not 0 <= start_seconds < duration
        ):
            raise ValueError("Invalid transcription range")
        if len(ids) != len(set(ids)) or any(
            segment["start"] < start_seconds
            or segment["end"] < segment["start"]
            or segment["end"] > duration + 0.02
            for segment in segments
        ):
            raise ValueError("Invalid transcription segment timestamps or IDs")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".run-{run_id}"
        staging.mkdir(exist_ok=False)
        try:
            manifest = {
                "schema_version": 1,
                "run_id": run_id,
                "created_at": datetime.now(UTC).isoformat(),
                "model_id": model.id,
                "model_repository": model.repository,
                "model_revision": model.revision,
                "selected_language": language,
                "detected_language": info.get("detected_language"),
                "duration_seconds": info.get("duration"),
                "start_seconds": info.get("start_seconds", 0.0),
            }
            _write_json(staging / "manifest.json", manifest)
            _write_json(staging / "original.json", segments)
            _write_json(staging / "working.json", segments)
            os.replace(staging, target)
            self.meetings.update_metadata(meeting_id, active_run=run_id)
        except Exception:
            for directory in (staging,):
                if directory.exists():
                    for name in ("manifest.json", "original.json", "working.json"):
                        (directory / name).unlink(missing_ok=True)
                    directory.rmdir()
            raise

    def list_runs(self, meeting_id: str) -> list[dict]:
        directory = self.meetings._meeting_dir(meeting_id) / "transcripts"
        if not directory.exists():
            return []
        result = []
        for child in directory.iterdir():
            if not child.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", child.name):
                continue
            try:
                with (child / "manifest.json").open(encoding="utf-8") as file:
                    result.append(json.load(file))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def read_run(self, meeting_id: str, run_id: str) -> dict:
        directory = self._run_dir(meeting_id, run_id)
        result = {}
        for name in ("manifest", "original", "working"):
            with (directory / f"{name}.json").open(encoding="utf-8") as file:
                result[name] = json.load(file)
        return result

    def active_run(self, meeting_id: str) -> dict | None:
        run_id = self.meetings.metadata(meeting_id).get("active_run")
        return self.read_run(meeting_id, run_id) if run_id else None

    def select_run(self, meeting_id: str, run_id: str) -> None:
        self.read_run(meeting_id, run_id)
        self.meetings.update_metadata(meeting_id, active_run=run_id)

    def save_edits(self, meeting_id: str, run_id: str, edits: dict[int, str]) -> None:
        data = self.read_run(meeting_id, run_id)
        original_ids = {segment["id"] for segment in data["original"]}
        if not set(edits).issubset(original_ids):
            raise ValueError("An edit refers to an unknown transcript segment")
        if any(not isinstance(text, str) for text in edits.values()):
            raise TypeError("Transcript edits must contain text")
        working = data["working"]
        for segment in working:
            if segment["id"] in edits:
                segment["text"] = edits[segment["id"]]
        _write_json(self._run_dir(meeting_id, run_id) / "working.json", working)
