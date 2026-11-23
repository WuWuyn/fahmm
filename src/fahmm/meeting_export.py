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
                line = f"{item['task']} · Người phụ trách: {item['owner']} · Hạn: {item['due_date']}"
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


def _render_denso_minutes(content: dict) -> str:
    """Render source-linked local AI claims in the supplied meeting-minutes form."""
    domain = content["domain"]
    metadata = domain["metadata"]
    sections = domain["sections"]

    def value(name: str) -> str:
        raw = metadata[name]["value"]
        return ", ".join(raw) if isinstance(raw, list) and raw else raw or "Chưa rõ"

    def cell(text: str) -> str:
        return " ".join(str(text).replace("|", "/").split())

    def items(name: str) -> list[dict]:
        return [item for item in sections.get(name, []) if item["review_status"] != "rejected"]

    def table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
        return ["| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
                *("| " + " | ".join(cell(part) for part in row) + " |" for row in rows)]

    def two_columns(name: str, headers: tuple[str, str]) -> list[str]:
        rows = [(item["label"], item["text"]) for item in items(name)]
        return table(headers, rows or [("Chưa rõ", "Chưa có thông tin trong bản phiên âm.")])

    title = value("title")
    summary = items("summary")
    lines = ["# MEETING MINUTES", title, f"Dự án/khách hàng: {value('project_customer')}", "",
             *table(("Ngày họp", "Phạm vi", "Trạng thái"), [
                 (value("meeting_datetime"), value("objective"), "Dự thảo để các bên xác nhận")]),
             "", "## 1. Thông tin cuộc họp",
             *table(("Hạng mục", "Nội dung"), [
                 ("Tên cuộc họp", title), ("Thời gian", value("meeting_datetime")),
                 ("Địa điểm", "Chưa rõ"), ("Mục tiêu", value("objective"))]),
             "", "### 1.1. Thành phần tham gia",
             *table(("Nhóm tham gia", "Ghi nhận"), [("Thành phần tham gia", value("participants"))]),
             "", "## 2. Tóm tắt điều hành",
             cell(summary[0]["text"]) if summary else "Chưa có thông tin trong bản phiên âm."]
    overview = []
    for key, label in (("dashboard_layout", "Dashboard tổng quan"),
                       ("kpi_scope", "Phạm vi KPI"), ("sqdcm_kpis", "KPI SQDCM"),
                       ("color_alerts", "Cảnh báo màu"),
                       ("warehouse_model", "Mô hình 3D"), ("input_data", "Dữ liệu đầu vào"),
                       ("project_actions", "Công việc nhóm dự án"),
                       ("partner_support", "Đề nghị hỗ trợ")):
        overview.extend((f"{label} — {item['label']}" if item['label'] != "Chưa rõ" else label,
                         item["text"]) for item in items(key))
    lines.extend(["", *table(("Hạng mục", "Điều chỉnh thống nhất"),
                              overview or [("Chưa rõ", "Chưa có thông tin trong bản phiên âm.")])])
    decisions = items("decisions")
    lines.extend(["", "Kết luận ghi nhận: " + (cell(decisions[0]["text"]) if decisions else
                  "Chưa có kết luận được xác nhận trong bản phiên âm."),
                  "", "## 3. Bố cục Dashboard tổng quan và hiển thị 3D",
                  *two_columns("dashboard_layout", ("Hạng mục", "Nội dung thống nhất")),
                  "", "## 4. Chỉ số KPI SQDCM và cơ chế cảnh báo màu",
                  "### 4.1. Phạm vi số liệu",
                  *two_columns("kpi_scope", ("Hạng mục", "Nội dung"))])
    kpis = [(item["label"], item["text"], item["method"], item["data_source"],
             item["open_point"]) for item in items("sqdcm_kpis")]
    if kpis:
        lines.extend(["", "### 4.2. Nhóm chỉ số SQDCM",
                      *table(("Nhóm", "Thông tin cần theo dõi", "Cách tính / hiển thị",
                              "Nguồn dữ liệu", "Cần xác nhận"), kpis)])
    lines.extend(["", "### 4.3. Cơ chế cảnh báo màu sắc",
                  *two_columns("color_alerts", ("Hạng mục", "Nội dung thống nhất")),
                  "", "## 5. Mô hình 3D hiện trường và dữ liệu đầu vào",
                  "### 5.1. Góp ý điều chỉnh layout 3D",
                  *two_columns("warehouse_model", ("Hạng mục", "Điều chỉnh thống nhất")),
                  "", "### 5.2. Chuẩn hóa kích thước và dữ liệu đầu vào",
                  *two_columns("input_data", ("Hạng mục", "Dữ liệu cần chuẩn hóa")),
                  "", "## 6. Công việc phía nhóm dự án FPT triển khai"])
    actions = []
    for item in items("project_actions"):
        owner = item["owner"]
        task = item["text"] + (f" — Phụ trách: {owner}" if owner != "Chưa rõ" else "")
        actions.append((task, item["due_date"]))
    lines.extend(table(("Công việc cụ thể", "Thời hạn"),
                       actions or [("Chưa có thông tin trong bản phiên âm.", "Chưa rõ")]))
    lines.extend(["", "## 7. Đề nghị phía DENSO hỗ trợ",
                  *table(("Nội dung nhờ hỗ trợ",),
                         [(item["text"],) for item in items("partner_support")]
                         or [("Chưa có thông tin trong bản phiên âm.",)])])
    next_steps = items("next_steps")
    if next_steps:
        lines.extend(["", "## 8. Công việc tiếp theo",
                      *table(("Công việc tiếp theo",), [(item["text"],) for item in next_steps])])
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
    universal_sections = {"summary", "topics", "requirements", "decisions", "proposed_solutions",
                          "open_questions", "risks_blockers", "actions", "next_steps",
                          "technical_considerations"}
    for key, heading in DOMAIN_HEADINGS.items():
        if domain["meeting_type"] == "general" and key not in universal_sections:
            continue
        items = [
            item for item in domain["sections"].get(key, []) if item["review_status"] != "rejected"
        ]
        if not items and domain["meeting_type"] != "general":
            continue
        lines.extend(("", f"## {heading}"))
        if not items:
            lines.append("Chưa có thông tin trong bản phiên âm.")
            continue
        if key in {"actions", "next_steps"}:
            def table_cell(value: str) -> str:
                return " ".join(value.replace("|", "/").split())

            if key == "actions":
                lines.extend(("| Công việc | Người phụ trách | Thời hạn |", "| --- | --- | --- |"))
                lines.extend("| " + " | ".join(table_cell(str(value)) for value in
                             (item["text"], item["owner"], item["due_date"])) + " |" for item in items)
            else:
                lines.extend(("| Công việc tiếp theo |", "| --- |"))
                lines.extend(f"| {table_cell(item['text'])} |" for item in items)
            continue
        for item in items:
            line = f"- {item['text']}"
            if key == "actions":
                details = [
                    f"Người phụ trách: {item['owner']}" if item['owner'] != "Chưa rõ" else "",
                    f"Hạn: {item['due_date']}" if item['due_date'] != "Chưa rõ" else "",
                ]
                if any(details):
                    line += " — " + " · ".join(detail for detail in details if detail)
            lines.append(line)
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

    def _write_text(self, destination: Path | None, content: str, *, overwrite: bool) -> Path | None:
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
            destination, render_docx(self.minutes_markdown(meeting_id, version_id)),
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
