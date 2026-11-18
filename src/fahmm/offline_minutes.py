"""Deterministic, source-linked Vietnamese extractive minutes. No network imports."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter

from fahmm.minutes_domain import new_claim, new_domain_content
from fahmm.minutes_store import MinutesStore
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

UNKNOWN = "Chưa rõ"
DOMAIN_SECTION_LIMIT = 100
DECISION_WORDS = ("thống nhất", "quyết định", "đồng ý", "chốt", "nhất trí")
ACTION_WORDS = ("cần thực hiện", "cần làm", "giao cho", "phụ trách", "sẽ làm", "sẽ gửi")
QUESTION_WORDS = ("?", "chưa rõ", "cần làm rõ", "cần xác nhận")
RISK_WORDS = ("rủi ro", "nguy cơ", "blocker", "bị chặn", "vướng mắc", "phụ thuộc")
NEXT_STEP_WORDS = ("bước tiếp theo", "tiếp theo", "sau cuộc họp", "buổi sau", "sẽ tiếp tục")
STOP_WORDS = {
    "và",
    "là",
    "của",
    "cho",
    "với",
    "trong",
    "được",
    "các",
    "những",
    "một",
    "này",
    "đó",
    "thì",
    "đã",
    "sẽ",
    "cần",
    "có",
    "không",
}


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
    tokenized = [
        set(re.findall(r"\w+", segment["text"].casefold())) - STOP_WORDS for segment in segments
    ]
    frequency = Counter(token for tokens in tokenized for token in tokens)
    selected: list[int] = []
    covered: set[str] = set()
    for _ in range(min(limit, len(segments))):
        choices = [index for index in range(len(segments)) if index not in selected]
        if not choices:
            break
        best = max(
            choices,
            key=lambda index: (
                sum(1 / frequency[token] for token in tokenized[index] - covered),
                len(tokenized[index] - covered),
                -index,
            ),
        )
        selected.append(best)
        covered.update(tokenized[best])
    return [segments[index] for index in sorted(selected)]


def _chronological_topics(segments: list[dict], limit: int = 12) -> list[dict]:
    """Take representative excerpts across the complete recording, with a fixed output cap."""
    if len(segments) <= limit:
        chosen = segments
    else:
        start, end = segments[0]["start"], max(item["end"] for item in segments)
        width = max((end - start) / limit, 0.001)
        windows: list[list[dict]] = [[] for _ in range(limit)]
        for segment in segments:
            index = min(int((segment["start"] - start) / width), limit - 1)
            windows[index].append(segment)
        chosen = [candidate for window in windows if window
                  for candidate in _topic_segments(window, 1)]
    seen: set[str] = set()
    result = []
    for segment in chosen:
        key = " ".join(segment["text"].casefold().split())
        if key not in seen:
            seen.add(key)
            result.append(segment)
    return result


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
    decisions = [
        _item(run_id, segment)
        for segment in usable
        if any(word in segment["text"].casefold() for word in DECISION_WORDS)
    ]
    actions = [
        {
            "task": segment["text"],
            "owner": UNKNOWN,
            "due_date": UNKNOWN,
            "verification_status": "Chưa xác minh",
            "sources": [_reference(run_id, segment)],
        }
        for segment in usable
        if any(word in segment["text"].casefold() for word in ACTION_WORDS)
    ]
    questions = [
        _item(run_id, segment)
        for segment in usable
        if any(word in segment["text"].casefold() for word in QUESTION_WORDS)
    ]
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


def extract_domain_minutes(
    meeting: dict, run_id: str, segments: list[dict], meeting_type: str, topic_limit: int = 5
) -> dict:
    """Build cited candidates only; keyword matches are never verified facts."""
    usable = [
        segment
        for segment in segments
        if isinstance(segment.get("text"), str) and segment["text"].strip()
    ]
    if not usable:
        raise ValueError("A non-empty transcript is required for minutes")
    usable.sort(key=lambda segment: (segment["start"], segment["id"]))
    content = new_domain_content(meeting_type, title=meeting.get("name"))
    sections = content["domain"]["sections"]
    universal = meeting_type == "general"
    seen_by_section: dict[str, set[str]] = {}

    def append(section: str, item: dict) -> None:
        entries = sections.setdefault(section, [])
        key = " ".join(item["text"].casefold().split())
        seen = seen_by_section.setdefault(section, set())
        if key not in seen and len(entries) < (30 if universal else DOMAIN_SECTION_LIMIT):
            seen.add(key)
            entries.append(item)

    def cite(segment: dict, **fields: object) -> dict:
        source = {**_reference(run_id, segment), "excerpt": segment["text"]}
        return new_claim(segment["text"].strip(), "extractive", sources=[source], **fields)

    topics = _chronological_topics(usable) if universal else _topic_segments(usable, topic_limit)
    summary = ([topics[0], topics[len(topics) // 2], topics[-1]] if universal and len(topics) >= 3
               else topics[:3])
    sections["summary"] = [cite(segment) for segment in {item["id"]: item for item in summary}.values()]
    sections["topics"] = [cite(segment) for segment in topics]
    for segment in usable:
        lower = segment["text"].casefold()
        if any(word in lower for word in QUESTION_WORDS):
            append("open_questions", cite(segment))
        if universal and any(word in lower for word in RISK_WORDS):
            kind = "blocker" if any(word in lower for word in ("blocker", "bị chặn", "vướng mắc")) else "risk"
            if "phụ thuộc" in lower:
                kind = "dependency"
            append("risks_blockers", cite(segment, kind=kind))
        if universal and any(word in lower for word in NEXT_STEP_WORDS):
            append("next_steps", cite(segment))
        if any(word in lower for word in ACTION_WORDS):
            append(
                "actions",
                cite(segment, owner=UNKNOWN, due_date=UNKNOWN, confirmation_status="suggested"),
            )
        if any(word in lower for word in DECISION_WORDS) and not any(
            word in lower
            for word in (
                "chưa thống nhất",
                "không thống nhất",
                "chưa quyết định",
                "chưa chốt",
                "không đồng ý",
                "proposed",
                "đề xuất",
                "phương án",
            )
        ):
            append("decisions", cite(segment))
        elif any(word in lower for word in ("đề xuất", "phương án", "alternative", "proposal")):
            append("proposed_solutions", cite(segment))

        if meeting_type in ("general", "requirement_gathering") and any(
            word in lower for word in ("yêu cầu", "hệ thống phải", "cần có", "requirement")
        ):
            kind = "business_rule" if "quy tắc" in lower else "functional"
            append("requirements", cite(segment, kind=kind, formality="candidate"))
        if meeting_type in ("general", "technical_discussion"):
            technical = {
                "api_integration": ("api", "integration", "tích hợp"),
                "database": ("database", "cơ sở dữ liệu"),
                "security": ("security", "bảo mật"),
                "performance": ("performance", "hiệu năng"),
                "alternative": ("alternative", "phương án", "lựa chọn"),
                "architecture": ("kiến trúc", "architecture"),
            }
            kind = next(
                (name for name, words in technical.items() if any(word in lower for word in words)),
                None,
            )
            if kind:
                append("technical_considerations", cite(segment, kind=kind))
        if meeting_type == "project_status":
            status = {
                "milestone": ("mốc", "milestone"),
                "blocker": ("blocker", "bị chặn", "vướng"),
                "risk": ("rủi ro", "risk"),
                "progress": ("tiến độ", "hoàn thành", "progress"),
                "dependency": ("phụ thuộc", "dependency"),
            }
            kind = next(
                (name for name, words in status.items() if any(word in lower for word in words)),
                None,
            )
            if kind:
                append("status_updates", cite(segment, kind=kind))
        if meeting_type == "issue_incident":
            incident = {
                "suspected_cause": ("nghi do", "có thể do", "suspected cause"),
                "impact": ("ảnh hưởng", "impact"),
                "workaround": ("tạm thời", "workaround"),
                "problem": ("sự cố", "lỗi", "incident"),
            }
            kind = next(
                (name for name, words in incident.items() if any(word in lower for word in words)),
                None,
            )
            if kind:
                append("incident_findings", cite(segment, kind=kind))
        if meeting_type == "uat_feedback":
            uat = {
                "defect": ("không đạt", "thất bại", "failed", "bug", "lỗi"),
                "observed_result": ("kết quả", "observed", "thực tế"),
                "customer_feedback": ("phản hồi", "feedback"),
                "scenario": ("kịch bản", "scenario", "uat"),
            }
            kind = next(
                (name for name, words in uat.items() if any(word in lower for word in words)), None
            )
            if kind:
                append("uat_observations", cite(segment, kind=kind, acceptance_status="pending"))
    if universal:
        for section in ("summary", "topics", "requirements", "decisions", "proposed_solutions",
                        "open_questions", "risks_blockers", "actions", "next_steps",
                        "technical_considerations"):
            sections.setdefault(section, [])
    return content


class OfflineMinutesService:
    """Generate a new local version without constructing any provider client."""

    def __init__(self, meetings: MeetingStore) -> None:
        self.meetings = meetings
        self.transcripts = TranscriptStore(meetings)
        self.minutes = MinutesStore(meetings)

    def generate(
        self, meeting_id: str, run_id: str | None = None, *, meeting_type: str | None = None
    ) -> str:
        with self.meetings.activity(meeting_id, "offline_minutes"):
            return self._generate(meeting_id, run_id, meeting_type)

    def _generate(self, meeting_id: str, run_id: str | None, meeting_type: str | None) -> str:
        metadata = self.meetings.metadata(meeting_id)
        run_id = run_id or metadata.get("active_run")
        if not run_id:
            raise ValueError("Transcribe this meeting before creating minutes")
        run = self.transcripts.read_run(meeting_id, run_id)
        template = self.minutes.read_template(meeting_id)
        if meeting_type is None:
            content = extract_minutes(metadata, run_id, run["working"], template["topic_limit"])
            content["headings"] = copy.deepcopy(template["headings"])
            content["guidance"] = template["guidance"]
        else:
            content = extract_domain_minutes(
                metadata, run_id, run["working"], meeting_type, template["topic_limit"]
            )
        return self.minutes.save_version(
            meeting_id,
            run_id,
            "extractive",
            content,
            json.dumps(template, ensure_ascii=False, sort_keys=True),
        )
