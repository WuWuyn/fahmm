"""Pure formatting of saved meeting documents; no Qt or provider imports."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from fahmm.docx_export import render_docx
from fahmm.library import MeetingLibrary
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


_TIMESTAMP = r"\d{2,}:\d{2}:\d{2}\.\d"
_SAVED_SOURCE_NOTE = re.compile(rf"[ \t]*\(Nguồn: {_TIMESTAMP}(?:, {_TIMESTAMP})*\)")
# Older free-form edits can also include the legacy list renderer's seconds suffix.
_SAVED_LIST_SOURCE = re.compile(r"^(- [^\r\n]*?) \[\d+\.\ds(?:, \d+\.\ds)*\](?=\r?$)", re.MULTILINE)


def render_minutes(content: dict) -> str:
    """Render the saved minutes body used by review and export."""
    if content.get("user_text") is not None:
        text = _SAVED_SOURCE_NOTE.sub("", content["user_text"])
        return _SAVED_LIST_SOURCE.sub(r"\1", text)
    if content.get("domain_schema_version") == 1:
        if content.get("format") == "denso_warehouse":
            return _render_denso_minutes(content)
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
                    f"{item['task']} · Người phụ trách: {item['owner']} · Hạn: {item['due_date']}"
                )
            else:
                line = item["text"]
            parts.append(f"- {line}")
    return "\n".join(parts)


DOMAIN_HEADINGS = {
    "summary": "Tóm tắt",
    "topics": "Chủ đề và thảo luận",
    "requirements": "Yêu cầu ứng viên",
    "decisions": "Quyết định",
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


SECTION_INTRODUCTIONS = {
    "summary": "Phần này tóm tắt các nội dung được ghi nhận trong cuộc họp.",
    "topics": "Các nội dung thảo luận được ghi nhận như sau:",
    "requirements": "Các yêu cầu được ghi nhận như sau:",
    "decisions": "Các nội dung kết luận được ghi nhận như sau:",
    "proposed_solutions": "Các phương án được đề cập như sau:",
    "open_questions": "Các câu hỏi cần tiếp tục làm rõ gồm:",
    "risks_blockers": "Các rủi ro và trở ngại được ghi nhận gồm:",
    "actions": "Các công việc được ghi nhận trong bảng sau:",
    "next_steps": "Các bước tiếp theo được ghi nhận trong bảng sau:",
    "technical_considerations": "Các nội dung kỹ thuật được ghi nhận như sau:",
    "status_updates": "Các cập nhật được ghi nhận như sau:",
    "incident_findings": "Các ghi nhận về sự cố gồm:",
    "uat_observations": "Các ghi nhận về UAT gồm:",
    "dashboard_layout": "Các nội dung về bố cục được ghi nhận như sau:",
    "kpi_scope": "Các nội dung về phạm vi số liệu gồm:",
    "sqdcm_kpis": "Các nội dung về chỉ số được ghi nhận như sau:",
    "color_alerts": "Các nội dung về cảnh báo được ghi nhận như sau:",
    "warehouse_model": "Các nội dung về mô hình được ghi nhận như sau:",
    "input_data": "Các nội dung về dữ liệu đầu vào gồm:",
    "project_actions": "Các công việc dự án được ghi nhận trong bảng sau:",
    "partner_support": "Các nội dung hỗ trợ được ghi nhận như sau:",
}


def _section_introduction(domain: dict, name: str, *, has_items: bool) -> str | None:
    """Prefer an authored introduction, retaining its paragraph breaks and spaces."""
    authored = domain.get("section_introductions", {}).get(name)
    if isinstance(authored, str) and authored.strip():
        return authored
    return SECTION_INTRODUCTIONS.get(name) if has_items else None


def _append_introduction(lines: list[str], domain: dict, name: str, *, has_items: bool) -> None:
    introduction = _section_introduction(domain, name, has_items=has_items)
    if introduction is not None:
        lines.extend(("", introduction, ""))


def _table_cell(value: object) -> str:
    # Escape backslashes first so a literal backslash before a pipe survives
    # both Markdown parsing and the application's preview/Word parsers.
    text = " ".join(str(value).split())
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _action_table(items: list[dict], *, next_steps: bool = False) -> list[str]:
    if next_steps:
        return [
            "| Công việc tiếp theo |",
            "| --- |",
            *(f"| {_table_cell(item['text'])} |" for item in items),
        ]
    return [
        "| Công việc | Người phụ trách | Thời hạn |",
        "| --- | --- | --- |",
        *(
            "| "
            + " | ".join(_table_cell(item[field]) for field in ("text", "owner", "due_date"))
            + " |"
            for item in items
        ),
    ]


def _append_domain_section(lines: list[str], domain: dict, key: str, *, show_empty: bool) -> None:
    items = [
        item for item in domain["sections"].get(key, []) if item["review_status"] != "rejected"
    ]
    introduction = _section_introduction(domain, key, has_items=bool(items))
    if not items and introduction is None and not show_empty:
        return
    lines.extend(("", f"## {DOMAIN_HEADINGS[key]}"))
    _append_introduction(lines, domain, key, has_items=bool(items))
    if not items:
        lines.append("Chưa có thông tin trong bản phiên âm.")
    elif key in {"actions", "next_steps"}:
        lines.extend(_action_table(items, next_steps=key == "next_steps"))
    else:
        lines.extend(f"- {item['text']}" for item in items)


def _render_denso_minutes(content: dict) -> str:
    """Render source-linked local AI claims in the supplied meeting-minutes form."""
    domain = content["domain"]
    metadata = domain["metadata"]
    sections = domain["sections"]

    def value(name: str) -> str:
        raw = metadata[name]["value"]
        return ", ".join(raw) if isinstance(raw, list) and raw else raw or "Chưa rõ"

    def items(name: str) -> list[dict]:
        return [item for item in sections.get(name, []) if item["review_status"] != "rejected"]

    def table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
        return [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(_table_cell(part) for part in row) + " |" for row in rows),
        ]

    def form_text(item: dict, *, kpi: bool = False) -> str:
        label = item["label"]
        line = f"{label}: {item['text']}" if label != "Chưa rõ" else item["text"]
        details = []
        for field, heading in (
            ("method", "Cách tính / hiển thị"),
            ("data_source", "Nguồn dữ liệu"),
            ("open_point", "Cần xác nhận"),
            ("owner", "Người phụ trách"),
            ("due_date", "Thời hạn"),
        ):
            if item[field] != "Chưa rõ" or (
                kpi and field in {"method", "data_source", "open_point"}
            ):
                details.append(f"{heading}: {item[field]}")
        return line + (" — " + "; ".join(details) if details else "")

    def text_section(name: str, heading: str, *, optional: bool = False, form: bool = False):
        claims = items(name)
        introduction = _section_introduction(domain, name, has_items=bool(claims))
        if optional and not claims and introduction is None:
            return
        lines.extend(("", heading))
        _append_introduction(lines, domain, name, has_items=bool(claims))
        if not claims:
            lines.append("Chưa có thông tin trong bản phiên âm.")
        else:
            lines.extend(
                f"- {form_text(item, kpi=name == 'sqdcm_kpis') if form else item['text']}"
                for item in claims
            )

    title = value("title")
    lines = [
        "# MEETING MINUTES",
        "",
        "## 1. Thông tin cuộc họp",
        f"Tên cuộc họp: {title}",
        f"Dự án/khách hàng: {value('project_customer')}",
        f"Thời gian: {value('meeting_datetime')}",
        "Địa điểm: Chưa rõ",
        f"Mục tiêu: {value('objective')}",
        f"Thành phần tham gia: {value('participants')}",
        "Trạng thái: Dự thảo để các bên xác nhận",
    ]
    text_section("summary", "## 2. Tóm tắt điều hành")
    text_section("decisions", "### Kết luận ghi nhận", optional=True)
    text_section("dashboard_layout", "## 3. Bố cục Dashboard tổng quan và hiển thị 3D", form=True)
    lines.extend(("", "## 4. Chỉ số KPI SQDCM và cơ chế cảnh báo màu"))
    text_section("kpi_scope", "### 4.1. Phạm vi số liệu", form=True)
    text_section("sqdcm_kpis", "### 4.2. Nhóm chỉ số SQDCM", optional=True, form=True)
    text_section("color_alerts", "### 4.3. Cơ chế cảnh báo màu sắc", form=True)
    lines.extend(("", "## 5. Mô hình 3D hiện trường và dữ liệu đầu vào"))
    text_section("warehouse_model", "### 5.1. Góp ý điều chỉnh layout 3D", form=True)
    text_section("input_data", "### 5.2. Chuẩn hóa kích thước và dữ liệu đầu vào", form=True)

    # Render any general claims too, even when the AI selected the form format.
    for key in DOMAIN_HEADINGS:
        if key not in {"summary", "decisions", "next_steps"}:
            _append_domain_section(lines, domain, key, show_empty=False)

    project_actions = items("project_actions")
    lines.extend(("", "## 6. Công việc phía nhóm dự án"))
    _append_introduction(lines, domain, "project_actions", has_items=bool(project_actions))
    if project_actions:
        rows = []
        for item in project_actions:
            # Keep all form fields while the responsible person and deadline get their own columns.
            task = form_text({**item, "owner": "Chưa rõ", "due_date": "Chưa rõ"})
            rows.append((task, item["owner"], item["due_date"]))
        lines.extend(table(("Công việc", "Người phụ trách", "Thời hạn"), rows))
    else:
        lines.append("Chưa có thông tin trong bản phiên âm.")
    text_section("partner_support", "## 7. Nội dung đề nghị hỗ trợ", form=True)

    next_steps = items("next_steps")
    if next_steps or _section_introduction(domain, "next_steps", has_items=False):
        lines.extend(("", "## 8. Công việc tiếp theo"))
        _append_introduction(lines, domain, "next_steps", has_items=bool(next_steps))
        lines.extend(
            _action_table(next_steps, next_steps=True)
            if next_steps
            else ["Chưa có thông tin trong bản phiên âm."]
        )
    lines.extend(["", "— HẾT —"])
    return "\n".join(lines)


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
    universal_sections = {
        "summary",
        "topics",
        "requirements",
        "decisions",
        "proposed_solutions",
        "open_questions",
        "risks_blockers",
        "actions",
        "next_steps",
        "technical_considerations",
    }
    for key in DOMAIN_HEADINGS:
        _append_domain_section(
            lines,
            domain,
            key,
            show_empty=domain["meeting_type"] == "general" and key in universal_sections,
        )
    return "\n".join(lines)


class MeetingExportService:
    def __init__(self, meetings: MeetingStore, model_root: Path | None = None) -> None:
        self.meetings = meetings
        self.minutes = MinutesStore(meetings)
        self.transcripts = TranscriptStore(meetings)
        self.library = MeetingLibrary(meetings)
        self._managed_roots = (
            meetings.root.resolve(),
            (model_root or meetings.root.parent / "models").resolve(),
        )

    def _validated_target(self, destination: Path, *, overwrite: bool) -> Path:
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
        return target

    def _write_bytes(
        self, destination: Path | None, content: bytes, *, overwrite: bool
    ) -> Path | None:
        if destination is None:
            return None
        target = self._validated_target(destination, overwrite=overwrite)
        temporary = target.parent / f".{target.name}-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("wb") as file:
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

    def _write_text(
        self, destination: Path | None, content: str, *, overwrite: bool
    ) -> Path | None:
        return self._write_bytes(destination, content.encode("utf-8"), overwrite=overwrite)

    def export_minutes(
        self, meeting_id: str, version_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        return self._write_text(
            destination, self.minutes_markdown(meeting_id, version_id), overwrite=overwrite
        )

    def export_minutes_docx(
        self, meeting_id: str, version_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        if Path(destination).suffix.lower() != ".docx":
            raise ValueError("Choose a .docx export destination")
        return self._write_bytes(
            destination,
            render_docx(self.minutes_markdown(meeting_id, version_id)),
            overwrite=overwrite,
        )

    def export_transcript(
        self, meeting_id: str, run_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        return self._write_text(
            destination, self.transcript_text(meeting_id, run_id), overwrite=overwrite
        )

    def export_transcript_plain(
        self, meeting_id: str, run_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        return self._write_text(
            destination, self.transcript_plain_text(meeting_id, run_id), overwrite=overwrite
        )

    def transcript_plain_text(self, meeting_id: str, run_id: str) -> str:
        run = self.transcripts.read_run(meeting_id, run_id)
        lines = [segment["text"].strip() for segment in run["working"] if segment["text"].strip()]
        return "\n".join(lines) + "\n" if lines else ""

    def audio_info(self, meeting_id: str) -> dict[str, str]:
        source = self.library.audio_path(meeting_id)
        extension = source.suffix.lower()
        if extension not in {".wav", ".mp3", ".m4a", ".flac"} or source.stat().st_size == 0:
            raise ValueError("Meeting audio is missing or unsupported")
        return {"fileName": f"recording{extension}", "extension": extension[1:]}

    def export_audio(
        self, meeting_id: str, destination: Path | None, *, overwrite: bool = False
    ) -> Path | None:
        if destination is None:
            return None
        with self.meetings.activity(meeting_id, "audio_export"):
            source = self.library.audio_path(meeting_id)
            extension = self.audio_info(meeting_id)["extension"]
            if Path(destination).suffix.lower() != f".{extension}":
                raise ValueError(f"Choose a .{extension} export destination")
            target = self._validated_target(destination, overwrite=overwrite)
            temporary = target.parent / f".{target.name}-{uuid.uuid4().hex}.tmp"
            try:
                with source.open("rb") as input_file, temporary.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
                    output_file.flush()
                    os.fsync(output_file.fileno())
                if overwrite:
                    os.replace(temporary, target)
                else:
                    os.rename(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            return target

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
        body = render_minutes(content).rstrip()
        lines = []
        if manifest["origin"] == "extractive":
            lines.append("> Generation: Local transcript extraction; not a semantic AI summary.")
        elif manifest["origin"] == "local_llm":
            lines.append("> Generation: Local Ollama DENSO-form draft.")
        elif manifest["origin"] == "provider":
            lines.append("> Generation: Configured provider.")
        elif manifest["origin"] == "user_edit":
            if manifest.get("source_origin") == "extractive":
                lines.append("> Generation: Edited from locally extracted minutes.")
            elif manifest.get("source_origin") == "local_llm":
                lines.append("> Generation: Edited from local Ollama semantic minutes.")
            elif manifest.get("source_origin") == "provider":
                lines.append("> Generation: Edited from provider-generated minutes.")
            else:
                lines.append("> Generation: Edited minutes; original source unavailable.")
        lines.append(
            "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        )
        lines.extend(("", body))
        return "\n".join(lines).rstrip() + "\n"
