"""Conservative normalization of untrusted provider minutes output."""

from __future__ import annotations

import copy
import json

from fahmm.cloud_minutes import CloudRequestSnapshot
from fahmm.minutes_store import DEFAULT_TEMPLATE
from fahmm.offline_minutes import ACTION_WORDS, DECISION_WORDS, UNKNOWN


def _source_ids(item: dict) -> list[int]:
    values = item.get("source_ids", item.get("sources", []))
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        segment_id = value.get("segment_id") if isinstance(value, dict) else value
        if type(segment_id) is int:
            result.append(segment_id)
    return result


def _items(value: object, selected: dict[int, object]) -> list[dict]:
    if isinstance(value, str):
        value = [{"text": value}]
    if not isinstance(value, list):
        return []
    result = []
    for entry in value:
        item = {"text": entry} if isinstance(entry, str) else entry
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        text = item["text"].strip()
        if not text:
            continue
        ids = _source_ids(item)
        valid = bool(ids) and all(segment_id in selected for segment_id in ids)
        sources = (
            [
                {
                    "run_id": segment.run_id,
                    "segment_id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                }
                for segment in (selected[segment_id] for segment_id in ids)
            ]
            if valid
            else []
        )
        result.append({"text": text, "sources": sources, "needs_review": True})
    return result


def normalize_provider_minutes(raw: object, snapshot: CloudRequestSnapshot, meeting: dict) -> dict:
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError("Provider returned no usable minutes")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"summary": raw.strip()}
    elif isinstance(raw, dict):
        parsed = raw
    else:
        raise TypeError("Provider returned an unsupported minutes response")
    if not isinstance(parsed, dict):
        raise TypeError("Provider returned an unsupported minutes response")
    selected = {
        segment.id: _ReferencedSegment(snapshot.run_id, segment) for segment in snapshot.segments
    }
    summary = _items(parsed.get("summary", parsed.get("main_summary", [])), selected)
    topics = _items(parsed.get("topics", []), selected)
    decisions = _items(parsed.get("decisions", []), selected)
    action_items = parsed.get("actions", [])
    actions = []
    if isinstance(action_items, list):
        for raw_action in action_items:
            if not isinstance(raw_action, dict):
                continue
            task = raw_action.get("task", raw_action.get("text", ""))
            normalized = _items([{**raw_action, "text": task}], selected)
            if not normalized:
                continue
            item = normalized[0]
            cited = " ".join(selected[source["segment_id"]].text for source in item["sources"])
            owner = raw_action.get("owner")
            due = raw_action.get("due_date")
            actions.append(
                {
                    "task": item["text"],
                    "owner": owner
                    if isinstance(owner, str)
                    and owner.strip()
                    and owner.casefold() in cited.casefold()
                    else UNKNOWN,
                    "due_date": due
                    if isinstance(due, str) and due.strip() and due.casefold() in cited.casefold()
                    else UNKNOWN,
                    "verification_status": "Chưa xác minh",
                    "sources": item["sources"],
                    "needs_review": True,
                }
            )
    questions = _items(parsed.get("open_questions", []), selected)
    if not any(
        any(word in segment.text.casefold() for word in DECISION_WORDS)
        for segment in selected.values()
    ):
        decisions = []
    if not any(
        any(word in segment.text.casefold() for word in ACTION_WORDS)
        for segment in selected.values()
    ):
        actions = []
    title = meeting.get("name") or UNKNOWN
    if title == "Untitled meeting":
        title = UNKNOWN
    return {
        "title": title,
        "date": str(meeting.get("created_at", ""))[:10] or UNKNOWN,
        "attendees": UNKNOWN,
        "summary": summary,
        "topics": topics,
        "decisions": decisions or [{"text": UNKNOWN, "sources": [], "needs_review": True}],
        "actions": actions,
        "open_questions": questions,
        "headings": copy.deepcopy(DEFAULT_TEMPLATE["headings"]),
        "label": "Unverified · Provider draft",
    }


class _ReferencedSegment:
    def __init__(self, run_id: str, segment: object) -> None:
        self.run_id = run_id
        self.id = segment.id
        self.start = segment.start
        self.end = segment.end
        self.text = segment.text
