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
        if content.get("actions"):
            lines.append("> Action entries are suggestions, not assigned or tracked tasks.")
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
