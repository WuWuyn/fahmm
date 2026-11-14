"""Deterministic, source-linked Vietnamese extractive minutes. No network imports."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter

from fahmm.minutes_store import MinutesStore
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

UNKNOWN = "Chưa rõ"
DECISION_WORDS = ("thống nhất", "quyết định", "đồng ý", "chốt", "nhất trí")
ACTION_WORDS = ("cần thực hiện", "cần làm", "giao cho", "phụ trách", "sẽ làm", "sẽ gửi")
QUESTION_WORDS = ("?", "chưa rõ", "cần làm rõ", "cần xác nhận")
STOP_WORDS = {"và", "là", "của", "cho", "với", "trong", "được", "các", "những",
              "một", "này", "đó", "thì", "đã", "sẽ", "cần", "có", "không"}


def _reference(run_id: str, segment: dict) -> dict:
    return {
        "run_id": run_id,
        "segment_id": segment["id"],
        "start": segment["start"],
        "end": segment["end"],
    }


def _item(run_id: str, segment: dict) -> dict:
    return {"text": segment["text"].strip(), "sources": [_reference(run_id, segment)]}


def _topic_segments(segments: list[dict], limit: int = 5) -> list[dict]:
    tokenized = [set(re.findall(r"\w+", segment["text"].casefold())) - STOP_WORDS
                 for segment in segments]
    frequency = Counter(token for tokens in tokenized for token in tokens)
    selected: list[int] = []
    covered: set[str] = set()
    for _ in range(min(limit, len(segments))):
        choices = [index for index in range(len(segments)) if index not in selected]
        if not choices:
            break
        best = max(choices, key=lambda index: (
            sum(1 / frequency[token] for token in tokenized[index] - covered),
            len(tokenized[index] - covered),
            -index,
        ))
        selected.append(best)
        covered.update(tokenized[best])
    return [segments[index] for index in sorted(selected)]


def extract_minutes(meeting: dict, run_id: str, segments: list[dict], topic_limit: int = 5) -> dict:
    """Return cited excerpts; never infer facts absent from the supplied text."""
    usable = [
        {**segment, "text": segment["text"].strip()}
        for segment in segments
        if isinstance(segment.get("text"), str) and segment["text"].strip()
    ]
    if not usable:
        raise ValueError("A non-empty transcript is required for minutes")
    usable.sort(key=lambda segment: (segment["start"], segment["id"]))
    topics = [_item(run_id, segment) for segment in _topic_segments(usable, topic_limit)]
    decisions = [_item(run_id, segment) for segment in usable
                 if any(word in segment["text"].casefold() for word in DECISION_WORDS)]
    actions = [
        {"task": segment["text"], "owner": UNKNOWN, "due_date": UNKNOWN,
         "verification_status": "Chưa xác minh", "sources": [_reference(run_id, segment)]}
        for segment in usable
        if any(word in segment["text"].casefold() for word in ACTION_WORDS)
    ]
    questions = [_item(run_id, segment) for segment in usable
                 if any(word in segment["text"].casefold() for word in QUESTION_WORDS)]
    title = meeting.get("name") or UNKNOWN
    if title == "Untitled meeting":
        title = UNKNOWN
    return {
        "title": title,
        "date": str(meeting.get("created_at", ""))[:10] or UNKNOWN,
        "attendees": UNKNOWN,
        "summary": topics[:3],
        "topics": topics,
        "decisions": decisions or [{"text": UNKNOWN, "sources": []}],
        "actions": actions,
        "open_questions": questions,
        "label": "Unverified · Offline extractive draft",
    }


class OfflineMinutesService:
    """Generate a new local version without constructing any provider client."""

    def __init__(self, meetings: MeetingStore) -> None:
        self.meetings = meetings
        self.transcripts = TranscriptStore(meetings)
        self.minutes = MinutesStore(meetings)

    def generate(self, meeting_id: str, run_id: str | None = None) -> str:
        with self.meetings.activity(meeting_id, "offline_minutes"):
            return self._generate(meeting_id, run_id)

    def _generate(self, meeting_id: str, run_id: str | None) -> str:
        metadata = self.meetings.metadata(meeting_id)
        run_id = run_id or metadata.get("active_run")
        if not run_id:
            raise ValueError("Transcribe this meeting before creating minutes")
        run = self.transcripts.read_run(meeting_id, run_id)
        template = self.minutes.read_template(meeting_id)
        content = extract_minutes(metadata, run_id, run["working"], template["topic_limit"])
        content["headings"] = copy.deepcopy(template["headings"])
        content["guidance"] = template["guidance"]
        return self.minutes.save_version(
            meeting_id, run_id, "extractive", content,
            json.dumps(template, ensure_ascii=False, sort_keys=True),
        )
