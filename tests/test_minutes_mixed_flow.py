"""Save and export a version with narrative text and an action table."""

import copy
import uuid

from docx import Document

from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_domain import new_claim, new_domain_content
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


def test_edited_introductions_and_actions_survive_reopen_and_word_export(tmp_path):
    meetings = MeetingStore(tmp_path / "meetings")
    meeting_id = meetings.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(
        uuid.uuid4().hex, "fixture/model", "test", "MIT", "a" * 40, 1, tmp_path / "model"
    )
    TranscriptStore(meetings).save_run(
        meeting_id,
        run_id,
        model,
        "vi",
        {"duration": 3},
        [{"id": 1, "start": 0.0, "end": 2.0, "text": "Kiểm tra API."}],
    )
    content = new_domain_content()
    content["domain"]["sections"] = {
        "actions": [
            new_claim(
                "Kiểm tra API",
                "user_provided",
                owner="Lan",
                due_date="Chưa rõ",
                confirmation_status="suggested",
            )
        ],
        "next_steps": [new_claim("Trao đổi thêm", "user_provided")],
    }
    store = MinutesStore(meetings)
    first = store.save_version(meeting_id, run_id, "extractive", content, "default")
    edited = copy.deepcopy(content)
    edited["domain"]["section_introductions"] = {
        "actions": "Phần này ghi nhận các việc cần kiểm tra.",
        "next_steps": "Tiếp theo, các bên có thể trao đổi thêm.",
    }
    edited["domain"]["sections"]["actions"][0]["owner"] = "Minh"
    current = store.edit_domain_version(meeting_id, first, edited)
    assert MinutesStore(MeetingStore(meetings.root)).active_version(meeting_id)["content"] == edited

    exports = MeetingExportService(meetings)
    markdown_path, word_path = tmp_path / "minutes.md", tmp_path / "minutes.docx"
    exports.export_minutes(meeting_id, current, markdown_path)
    exports.export_minutes_docx(meeting_id, current, word_path)
    markdown = markdown_path.read_text(encoding="utf-8")
    first_intro = "Phần này ghi nhận các việc cần kiểm tra."
    second_intro = "Tiếp theo, các bên có thể trao đổi thêm."
    assert (
        markdown.index(first_intro)
        < markdown.index("| Kiểm tra API | Minh |")
        < markdown.index(second_intro)
    )
    document = Document(word_path)
    body = document.element.body
    blocks = [(child.tag.rsplit("}", 1)[-1], "".join(child.itertext())) for child in body]
    intro_index = next(i for i, (_, text) in enumerate(blocks) if first_intro in text)
    table_index = next(i for i, (tag, text) in enumerate(blocks) if tag == "tbl" and "Minh" in text)
    next_index = next(i for i, (_, text) in enumerate(blocks) if second_intro in text)
    assert intro_index < table_index < next_index
