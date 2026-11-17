"""Pure formatting of saved meeting documents; no Qt or provider imports."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fahmm.minutes_store import MinutesStore
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


def format_timestamp(seconds: float) -> str:
    whole, fraction = divmod(round(float(seconds) * 10), 10)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{fraction}"


def iter_citations(content: object):
    if isinstance(content, dict):
        yield from content.get("sources", [])
        for key, value in content.items():
            if key != "sources":
                yield from iter_citations(value)
    elif isinstance(content, list):
        for value in content:
            yield from iter_citations(value)


def render_minutes(content: dict) -> str:
    """Render the saved minutes body used by review and export."""
    if content.get("user_text") is not None:
        return content["user_text"]
    if content.get("domain_schema_version") == 1:
        return _render_domain_minutes(content)
    headings = content.get("headings", {})
    parts = [
        f"# {content.get('title', 'Chưa rõ')}",
        f"{headings.get('date', 'Ngày')}: {content.get('date', 'Chưa rõ')}",
        f"{headings.get('attendees', 'Người tham dự')}: {content.get('attendees', 'Chưa rõ')}",
    ]
    for key, fallback in (
        ("summary", "Tóm tắt"),
        ("topics", "Chủ đề và thảo luận"),
        ("decisions", "Quyết định"),
        ("actions", "Việc cần làm"),
        ("open_questions", "Câu hỏi và bước tiếp theo"),
    ):
        parts.append(f"\n## {headings.get(key, fallback)}")
        for item in content.get(key, []):
            if key == "actions":
                line = (
                    f"{item['task']} · Người phụ trách: {item['owner']} · "
                    f"Hạn: {item['due_date']} · {item['verification_status']}"
                )
            else:
                line = item["text"]
            stamps = ", ".join(f"{source['start']:.1f}s" for source in item.get("sources", []))
            parts.append(f"- {line}" + (f" [{stamps}]" if stamps else ""))
    return "\n".join(parts)


DOMAIN_HEADINGS = {
    "summary": "Tóm tắt",
    "topics": "Chủ đề và thảo luận",
    "requirements": "Yêu cầu ứng viên",
    "decisions": "Quyết định cần xác minh",
    "proposed_solutions": "Phương án đề xuất",
    "open_questions": "Câu hỏi còn mở",
    "risks_blockers": "Rủi ro và trở ngại",
    "actions": "Việc cần làm đề xuất",
    "next_steps": "Bước tiếp theo",
    "technical_considerations": "Nội dung kỹ thuật",
    "status_updates": "Cập nhật tiến độ",
    "incident_findings": "Ghi nhận sự cố",
    "uat_observations": "Ghi nhận UAT",
}
DOMAIN_MEETING_TYPE_LABELS = {
    "general": "Cuộc họp chung",
    "requirement_gathering": "Thu thập yêu cầu",
    "technical_discussion": "Thảo luận kỹ thuật",
    "project_status": "Cập nhật dự án",
    "issue_incident": "Vấn đề / sự cố",
    "uat_feedback": "Phản hồi UAT",
}
DOMAIN_REVIEW_LABELS = {
    "needs_review": "Cần xem lại",
    "confirmed": "Đã xác nhận",
    "rejected": "Đã loại",
}
DOMAIN_ORIGIN_LABELS = {
    "extractive": "Trích xuất từ phiên âm",
    "provider": "Bản nháp từ nhà cung cấp",
    "user_provided": "Người dùng cung cấp",
}
DOMAIN_CERTAINTY_LABELS = {
    "candidate": "Ứng viên",
    "user_confirmed": "Người dùng xác nhận",
    "pending": "Chờ xác nhận",
}


def _render_domain_minutes(content: dict) -> str:
    domain = content["domain"]
    metadata = domain["metadata"]

    def value(key: str):
        return metadata[key]["value"]

    participants = ", ".join(value("participants")) or "Chưa rõ"
    lines = [
        f"# {value('title') or 'Chưa rõ'}",
        f"Loại cuộc họp: {DOMAIN_MEETING_TYPE_LABELS[domain['meeting_type']]}",
        f"Ngày giờ họp: {value('meeting_datetime') or 'Chưa rõ'}",
        f"Dự án/khách hàng: {value('project_customer') or 'Chưa rõ'}",
        f"Người tham dự: {participants}",
        f"Mục tiêu: {value('objective') or 'Chưa rõ'}",
    ]
    for key, heading in DOMAIN_HEADINGS.items():
        items = [
            item for item in domain["sections"].get(key, []) if item["review_status"] != "rejected"
        ]
        if not items:
            continue
        lines.extend(("", f"## {heading}"))
        for item in items:
            qualifiers = [
                DOMAIN_REVIEW_LABELS[item["review_status"]],
                DOMAIN_ORIGIN_LABELS[item["origin"]],
            ]
            if "kind" in item:
                qualifiers.append(item["kind"])
            if "formality" in item:
                qualifiers.append(DOMAIN_CERTAINTY_LABELS[item["formality"]])
            if "acceptance_status" in item:
                qualifiers.append(
                    f"Trạng thái chấp nhận: {DOMAIN_CERTAINTY_LABELS[item['acceptance_status']]}"
                )
            if key == "actions":
                qualifiers.extend(
                    (
                        f"Người phụ trách: {item['owner']}",
                        f"Hạn: {item['due_date']}",
                        f"{'Đề xuất' if item['confirmation_status'] == 'suggested' else 'Đã xem lại'}; chưa phải công việc được theo dõi",
                    )
                )
            citations = ", ".join(
                f"đoạn {source['segment_id']} {format_timestamp(source['start'])}–{format_timestamp(source['end'])}"
                for source in item["sources"]
            )
            note = "; ".join(
                qualifiers + ([citations] if citations else ["không có nguồn phiên âm"])
            )
            lines.append(f"- {item['text']} ({note})")
    return "\n".join(lines)


class MeetingExportService:
    def __init__(self, meetings: MeetingStore, model_root: Path | None = None) -> None:
        self.minutes = MinutesStore(meetings)
        self.transcripts = TranscriptStore(meetings)
        self._managed_roots = (
            meetings.root.resolve(),
            (model_root or meetings.root.parent / "models").resolve(),
        )

    def _write_text(
        self, destination: Path | None, content: str, *, overwrite: bool
    ) -> Path | None:
        if destination is None:
            return None
        target = Path(destination)
        if not target.is_absolute():
            raise ValueError("Choose an absolute export destination")
        resolved = target.resolve(strict=False)
        if any(resolved.is_relative_to(root) for root in self._managed_roots):
            raise ValueError("Choose a location outside fahmm-managed meeting and model data")
        if not target.parent.is_dir():
            raise FileNotFoundError("Export destination folder does not exist")
        if target.exists() and not overwrite:
            raise FileExistsError("Confirm before replacing an existing export")
        temporary = target.parent / f".{target.name}-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            if overwrite:
                os.replace(temporary, target)
            else:
                # On Windows, rename refuses an existing destination, including one raced in.
                os.rename(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def export_minutes(
        self, meeting_id: str, version_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        return self._write_text(
            destination, self.minutes_markdown(meeting_id, version_id), overwrite=overwrite
        )

    def export_transcript(
        self, meeting_id: str, run_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        return self._write_text(
            destination, self.transcript_text(meeting_id, run_id), overwrite=overwrite
        )

    def transcript_text(self, meeting_id: str, run_id: str) -> str:
        run = self.transcripts.read_run(meeting_id, run_id)
        rows = [
            f"[{format_timestamp(segment['start'])}–{format_timestamp(segment['end'])}] "
            f"{segment['text']}"
            for segment in run["working"]
        ]
        return "\n".join(rows).rstrip() + "\n" if rows else ""

    def minutes_markdown(self, meeting_id: str, version_id: str) -> str:
        version = self.minutes.read_version(meeting_id, version_id)
        manifest, content = version["manifest"], version["content"]
        state = manifest["review_state"]
        if state not in ("approved", "unverified"):
            raise ValueError("Unknown minutes review state")
        body = render_minutes(content).rstrip()
        lines = [f"> Review state: {state.title()}"]
        if manifest["origin"] == "extractive":
            lines.append("> Draft type: Source-linked extractive draft; not a semantic AI summary.")
        elif manifest["origin"] == "provider":
            lines.append(
                "> Draft type: Provider-generated draft; verify claims against the source."
            )
        elif manifest["origin"] == "user_edit":
            if manifest.get("source_origin") == "extractive":
                lines.append(
                    "> Draft type: Edited from an offline extractive draft; "
                    "user edits have not been automatically verified."
                )
            elif manifest.get("source_origin") == "provider":
                lines.append(
                    "> Draft type: Edited from a provider-generated draft; "
                    "user edits have not been automatically verified."
                )
            else:
                lines.append(
                    "> Draft type: Edited version; original draft type unavailable. "
                    "User edits have not been automatically verified."
                )
        lines.append(
            "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        )
        lines.extend(("", body))
        if content.get("user_text") is not None:
            citations = {
                (source["segment_id"], source["start"], source["end"])
                for source in iter_citations(content)
            }
            if citations:
                lines.extend(
                    [
                        "",
                        "## Source references from the underlying draft",
                        "",
                        "These references do not automatically verify the edited text.",
                        "",
                    ]
                )
                for segment_id, start, end in sorted(
                    citations, key=lambda item: (item[1], item[0])
                ):
                    lines.append(
                        f"- Segment {segment_id}: {format_timestamp(start)}–{format_timestamp(end)}"
                    )
        return "\n".join(lines).rstrip() + "\n"
