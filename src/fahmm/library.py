"""Filesystem-backed local meeting index and user-visible metadata operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fahmm.storage import MeetingStore


@dataclass(frozen=True)
class MeetingSummary:
    id: str
    name: str
    created_at: str
    source_kind: str
    recording_state: str
    processing_state: str
    privacy_mode: str

    @property
    def status(self) -> str:
        return (
            self.recording_state if self.recording_state != "completed" else self.processing_state
        )


class MeetingLibrary:
    def __init__(self, store: MeetingStore) -> None:
        self.store = store

    def list_meetings(self) -> list[MeetingSummary]:
        if not self.store.root.exists():
            return []
        result = []
        for directory in self.store.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                data = self.store.metadata(directory.name)
                result.append(self._summary(data))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(result, key=lambda item: (item.created_at, item.id), reverse=True)

    def get(self, meeting_id: str) -> MeetingSummary:
        return self._summary(self.store.metadata(meeting_id))

    def rename(self, meeting_id: str, name: str) -> MeetingSummary:
        name = name.strip()
        if not name or len(name) > 120 or any(ord(char) < 32 for char in name):
            raise ValueError("Enter a meeting name of 1–120 characters without control characters")
        return self._summary(self.store.update_metadata(meeting_id, name=name))

    def set_privacy_mode(self, meeting_id: str, mode: str) -> MeetingSummary:
        self.store.set_privacy_mode(meeting_id, mode)
        return self.get(meeting_id)

    def audio_path(self, meeting_id: str) -> Path:
        data = self.store.metadata(meeting_id)
        if data["state"] != "completed":
            raise ValueError("Finish or recover this recording before opening its audio")
        name = data["audio_file"]
        if not isinstance(name, str) or Path(name).name != name or name.startswith("."):
            raise ValueError("Invalid meeting audio path")
        path = self.store._meeting_dir(meeting_id) / name
        if not path.resolve(strict=False).is_relative_to(
            self.store._meeting_dir(meeting_id).resolve()
        ):
            raise ValueError("Meeting audio must stay inside its local meeting folder")
        if not path.is_file():
            raise FileNotFoundError("Meeting audio is missing")
        return path

    @staticmethod
    def _summary(data: dict) -> MeetingSummary:
        return MeetingSummary(
            id=data["id"],
            name=data["name"],
            created_at=data["created_at"],
            source_kind=data["source_kind"],
            recording_state=data["state"],
            processing_state=data["processing_state"],
            privacy_mode=data["privacy_mode"],
        )
