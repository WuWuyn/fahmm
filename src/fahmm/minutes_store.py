"""Atomic, versioned minutes stored alongside each local meeting."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fahmm.minutes_domain import MEETING_TYPES, validate_domain_content
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

ID_RE = re.compile(r"[0-9a-f]{32}\Z")
DEFAULT_TEMPLATE = {
    "headings": {
        "title": "Tiêu đề",
        "date": "Ngày",
        "attendees": "Người tham dự",
        "summary": "Tóm tắt",
        "topics": "Chủ đề và thảo luận",
        "decisions": "Quyết định",
        "actions": "Việc cần làm",
        "open_questions": "Câu hỏi và bước tiếp theo",
    },
    "guidance": "Review every excerpt against its source before approving the minutes.",
    "topic_limit": 5,
}


def _atomic_json(path: Path, data: dict) -> None:
    temporary = path.parent / f".{path.name}-{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class MinutesStore:
    def __init__(self, meetings: MeetingStore) -> None:
        self.meetings = meetings
        self.transcripts = TranscriptStore(meetings)

    def _version_dir(self, meeting_id: str, version_id: str) -> Path:
        if not ID_RE.fullmatch(version_id):
            raise ValueError("Invalid minutes version ID")
        return self.meetings._meeting_dir(meeting_id) / "minutes" / version_id

    def read_template(self, meeting_id: str) -> dict:
        path = self.meetings._meeting_dir(meeting_id) / "minutes" / "template.json"
        if not path.exists():
            return copy.deepcopy(DEFAULT_TEMPLATE)
        with path.open(encoding="utf-8") as file:
            template = json.load(file)
        self._validate_template(template)
        return template

    def save_template(self, meeting_id: str, template: dict) -> None:
        self._validate_template(template)
        directory = self.meetings._meeting_dir(meeting_id) / "minutes"
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_json(directory / "template.json", template)

    @staticmethod
    def _validate_template(template: object) -> None:
        if not isinstance(template, dict):
            raise TypeError("Invalid minutes template")
        headings = template.get("headings")
        if not isinstance(headings, dict) or set(headings) != set(DEFAULT_TEMPLATE["headings"]):
            raise ValueError("Invalid minutes headings")
        if any(not isinstance(value, str) or not value.strip() for value in headings.values()):
            raise ValueError("Minutes headings must contain text")
        if not isinstance(template.get("guidance"), str):
            raise TypeError("Invalid minutes guidance")
        limit = template.get("topic_limit")
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("Topic limit must be between 1 and 10")

    def save_version(
        self,
        meeting_id: str,
        run_id: str,
        origin: str,
        content: dict,
        template: str,
        provider_id: str | None = None,
        *,
        parent_version_id: str | None = None,
    ) -> str:
        if origin not in ("extractive", "local_llm", "provider", "user_edit"):
            raise ValueError("Invalid minutes origin")
        if not isinstance(content, dict) or not isinstance(template, str):
            raise TypeError("Invalid minutes content")
        if "domain_schema_version" in content or "domain" in content:
            validate_domain_content(content)
        if origin == "user_edit":
            if parent_version_id is None:
                raise ValueError("Edited minutes require a parent version")
            parent_manifest = self.read_version(meeting_id, parent_version_id)["manifest"]
            if parent_manifest["run_id"] != run_id:
                raise ValueError("Edited minutes must use the parent transcript run")
            source_origin = parent_manifest.get("source_origin")
            if source_origin not in ("extractive", "local_llm", "provider"):
                source_origin = (
                    parent_manifest["origin"]
                    if parent_manifest["origin"] in ("extractive", "local_llm", "provider")
                    else None
                )
        else:
            if parent_version_id is not None:
                raise ValueError("Only edited minutes can have a parent version")
            source_origin = origin
        run = self.transcripts.read_run(meeting_id, run_id)
        valid_ids = {segment["id"] for segment in run["working"]}
        self._validate_sources(content, run_id, valid_ids)
        if "domain_schema_version" in content:
            self._validate_domain_sources(content, run_id, run["working"])
        version_id = uuid.uuid4().hex
        target = self._version_dir(meeting_id, version_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".version-{version_id}"
        staging.mkdir(exist_ok=False)
        manifest = {
            "schema_version": 2,
            "version_id": version_id,
            "run_id": run_id,
            "origin": origin,
            "parent_version_id": parent_version_id,
            "source_origin": source_origin,
            "provider_id": provider_id,
            "created_at": datetime.now(UTC).isoformat(),
            "review_state": "unverified",
            "template": template,
        }
        try:
            _atomic_json(staging / "manifest.json", manifest)
            _atomic_json(staging / "content.json", content)
            os.replace(staging, target)
            self.meetings.update_metadata(meeting_id, active_minutes_version=version_id)
        finally:
            if staging.exists():
                for name in ("manifest.json", "content.json"):
                    (staging / name).unlink(missing_ok=True)
                staging.rmdir()
        return version_id

    @staticmethod
    def _validate_sources(value: object, run_id: str, valid_ids: set[int]) -> None:
        if isinstance(value, dict):
            if "sources" in value:
                sources = value["sources"]
                if not isinstance(sources, list):
                    raise ValueError("Invalid minutes source list")
                for source in sources:
                    if not isinstance(source, dict) or source.get("run_id") != run_id:
                        raise ValueError("Invalid minutes source run")
                    if source.get("segment_id") not in valid_ids:
                        raise ValueError("Invalid minutes source segment")
                    start, end = source.get("start"), source.get("end")
                    if (
                        not isinstance(start, (float, int))
                        or not isinstance(end, (float, int))
                        or start < 0
                        or end < start
                    ):
                        raise ValueError("Invalid minutes source timestamp")
            for child in value.values():
                MinutesStore._validate_sources(child, run_id, valid_ids)
        elif isinstance(value, list):
            for child in value:
                MinutesStore._validate_sources(child, run_id, valid_ids)

    @staticmethod
    def _domain_source_fields(content: dict):
        domain = content["domain"]
        for name, field in domain["metadata"].items():
            yield f"metadata.{name}", field["sources"]
        for section, items in domain["sections"].items():
            for item in items:
                yield f"sections.{section}.{item['item_id']}", item["sources"]

    @classmethod
    def _validate_domain_sources(cls, content: dict, run_id: str, segments: list[dict]) -> None:
        by_id = {segment["id"]: segment for segment in segments}
        for location, sources in cls._domain_source_fields(content):
            for source in sources:
                if not isinstance(source, dict) or set(source) != {
                    "run_id",
                    "segment_id",
                    "start",
                    "end",
                    "excerpt",
                }:
                    raise ValueError(f"Invalid {location} source fields")
                segment = by_id.get(source["segment_id"])
                if segment is None or source["run_id"] != run_id:
                    raise ValueError(f"Invalid {location} source segment")
                if (
                    type(source["start"]) not in (int, float)
                    or type(source["end"]) not in (int, float)
                    or source["start"] != segment["start"]
                    or source["end"] != segment["end"]
                ):
                    raise ValueError(f"Invalid {location} source timestamp")
                if (
                    not isinstance(source["excerpt"], str)
                    or not source["excerpt"].strip()
                    or source["excerpt"] != segment["text"]
                ):
                    raise ValueError(f"Invalid {location} source excerpt")

    def source_drift(self, meeting_id: str, version_id: str) -> list[dict]:
        """Compare a saved version's evidence snapshots with its current working transcript."""
        version = self.read_version(meeting_id, version_id)
        content = version["content"]
        if "domain_schema_version" not in content:
            return []
        run_id = version["manifest"]["run_id"]
        current = {s["id"]: s for s in self.transcripts.read_run(meeting_id, run_id)["working"]}
        result = []
        for location, sources in self._domain_source_fields(content):
            for source in sources:
                segment = current.get(source["segment_id"])
                current_text = segment["text"] if segment is not None else None
                result.append(
                    {
                        "location": location,
                        "source": source,
                        "current_text": current_text,
                        "drifted": segment is None
                        or segment["start"] != source["start"]
                        or segment["end"] != source["end"]
                        or current_text != source["excerpt"],
                    }
                )
        return result

    def read_version(self, meeting_id: str, version_id: str) -> dict:
        directory = self._version_dir(meeting_id, version_id)
        result = {}
        for name in ("manifest", "content"):
            with (directory / f"{name}.json").open(encoding="utf-8") as file:
                result[name] = json.load(file)
        return result

    def list_versions(self, meeting_id: str) -> list[dict]:
        parent = self.meetings._meeting_dir(meeting_id) / "minutes"
        if not parent.exists():
            return []
        result = []
        for child in parent.iterdir():
            if not child.is_dir() or not ID_RE.fullmatch(child.name):
                continue
            try:
                result.append(self.read_version(meeting_id, child.name)["manifest"])
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return sorted(
            result, key=lambda item: (item["created_at"], item["version_id"]), reverse=True
        )

    def active_version(self, meeting_id: str) -> dict | None:
        version_id = self.meetings.metadata(meeting_id).get("active_minutes_version")
        return self.read_version(meeting_id, version_id) if version_id else None

    def select_version(self, meeting_id: str, version_id: str) -> None:
        self.read_version(meeting_id, version_id)
        self.meetings.update_metadata(meeting_id, active_minutes_version=version_id)

    def edit_version(self, meeting_id: str, version_id: str, content: dict) -> str:
        prior = self.read_version(meeting_id, version_id)
        manifest = prior["manifest"]
        return self.save_version(
            meeting_id,
            manifest["run_id"],
            "user_edit",
            copy.deepcopy(content),
            manifest["template"],
            manifest["provider_id"],
            parent_version_id=version_id,
        )

    def edit_domain_version(self, meeting_id: str, version_id: str, content: dict) -> str:
        active = self.meetings.metadata(meeting_id).get("active_minutes_version")
        if active != version_id:
            raise ValueError("Select the latest minutes version before editing")
        prior = self.read_version(meeting_id, version_id)
        if "domain_schema_version" not in prior["content"]:
            raise ValueError("This is a legacy minutes version")
        validate_domain_content(content)
        return self.edit_version(meeting_id, version_id, content)

    def set_domain_type(self, meeting_id: str, version_id: str, meeting_type: str) -> str:
        if not isinstance(meeting_type, str) or meeting_type not in MEETING_TYPES:
            raise ValueError("Invalid meeting type")
        content = copy.deepcopy(self.read_version(meeting_id, version_id)["content"])
        if "domain_schema_version" not in content:
            raise ValueError("This is a legacy minutes version")
        content["domain"]["meeting_type"] = meeting_type
        for section in (
            "requirements",
            "technical_considerations",
            "status_updates",
            "incident_findings",
            "uat_observations",
        ):
            content["domain"]["sections"].pop(section, None)
        return self.edit_domain_version(meeting_id, version_id, content)

    def approve_version(self, meeting_id: str, version_id: str) -> None:
        data = self.read_version(meeting_id, version_id)
        manifest = data["manifest"]
        if manifest["review_state"] == "approved":
            return
        if "domain_schema_version" in data["content"]:
            for items in data["content"]["domain"]["sections"].values():
                if any(item["review_status"] == "needs_review" for item in items):
                    raise ValueError("Review every minutes claim before approval")
            if any(
                entry["drifted"]
                and not self._source_belongs_to_rejected_claim(data["content"], entry["location"])
                for entry in self.source_drift(meeting_id, version_id)
            ):
                raise ValueError("Transcript source changed; review and save a new version")
        manifest["review_state"] = "approved"
        _atomic_json(self._version_dir(meeting_id, version_id) / "manifest.json", manifest)

    @staticmethod
    def _source_belongs_to_rejected_claim(content: dict, location: str) -> bool:
        parts = location.split(".")
        if len(parts) != 3 or parts[0] != "sections":
            return False
        return any(
            item["item_id"] == parts[2] and item["review_status"] == "rejected"
            for item in content["domain"]["sections"].get(parts[1], [])
        )
