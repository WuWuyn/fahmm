"""Saved minutes formatting stays independent of the Qt review widget."""

import copy
import socket
import uuid
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import pytest
from test_minutes_store import make_meeting_with_run, sample_content

from fahmm import meeting_export
from fahmm.docx_export import render_docx
from fahmm.meeting_export import MeetingExportService, render_minutes
from fahmm.minutes_domain import new_claim, new_domain_content
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.transcripts import TranscriptStore


def test_word_renderer_preserves_form_tables():
    from io import BytesIO

    document = render_docx(
        "# MEETING MINUTES\n\n| Hạng mục | Nội dung |\n| --- | --- |\n| Mục tiêu | Review demo |"
    )
    with ZipFile(BytesIO(document)) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    table = root.find(".//w:tbl", ns)
    assert table is not None
    assert len(table.findall("w:tr", ns)) == 2
    assert [node.text for node in table.findall(".//w:t", ns)] == [
        "Hạng mục",
        "Nội dung",
        "Mục tiêu",
        "Review demo",
    ]


def test_explicit_minutes_versions_export_without_review_state(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    approved = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    versions.approve_version(meeting_id, approved)
    newer = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id, "Bản chưa duyệt"), "default"
    )

    service = MeetingExportService(meetings)
    first = service.minutes_markdown(meeting_id, approved)
    second = service.minutes_markdown(meeting_id, newer)
    assert "Review state:" not in first
    assert "> Generation: Local transcript extraction; not a semantic AI summary." in first
    assert "Đã thống nhất thử nghiệm." in first
    assert "[0.0s]" not in first
    assert "Bản chưa duyệt" not in first
    assert "Review state:" not in second
    assert "Bản chưa duyệt" in second


def test_word_export_uses_selected_saved_version_without_review_notice(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    versions = MinutesStore(meetings)
    older = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    newer = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id, "Bản mới"), "default"
    )
    destination = tmp_path / "minutes.docx"
    service = MeetingExportService(meetings)
    assert service.export_minutes_docx(meeting_id, newer, destination) == destination
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert {
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
            "word/styles.xml",
            "word/_rels/document.xml.rels",
        } <= set(archive.namelist())
        root = ET.fromstring(archive.read("word/document.xml"))
    text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    assert "Bản mới" in text
    assert "Đã thống nhất thử nghiệm." not in text
    assert "Review state:" not in text
    assert "Any action items in these minutes are suggestions" in text
    assert "[0.0s]" not in text
    with pytest.raises(FileExistsError, match="Confirm"):
        service.export_minutes_docx(meeting_id, older, destination)
    with pytest.raises(ValueError, match=".docx"):
        service.export_minutes_docx(meeting_id, older, tmp_path / "wrong.md")


def test_export_labels_action_entries_as_suggestions(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    content = sample_content(run_id)
    content["actions"] = [
        {
            "task": "Kiểm tra thử nghiệm",
            "owner": "Chưa rõ",
            "due_date": "Chưa rõ",
            "verification_status": "Chưa xác minh",
            "sources": [
                {
                    "run_id": run_id,
                    "segment_id": 1,
                    "start": 0.0,
                    "end": 2.0,
                }
            ],
        }
    ]
    version = MinutesStore(meetings).save_version(
        meeting_id, run_id, "extractive", content, "default"
    )
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, version)
    assert (
        "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        in markdown
    )
    assert "Kiểm tra thử nghiệm" in markdown


def test_universal_draft_export_includes_empty_sections(tmp_path):
    meetings, meeting_id, _run_id = make_meeting_with_run(tmp_path)
    version_id = OfflineMinutesService(meetings).generate(meeting_id, meeting_type="general")
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, version_id)
    assert "## Tóm tắt" in markdown
    assert "## Yêu cầu ứng viên" in markdown
    assert "## Quyết định" in markdown
    assert "Chưa có thông tin trong bản phiên âm." in markdown
    assert "Cần xem lại" not in markdown
    assert "## Ghi nhận UAT" not in markdown


def test_edited_minutes_omit_saved_timestamp_notes_and_export_appendix(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    content = sample_content(run_id)
    clean = (
        "# Biên bản đã sửa\r\nQuyết định cần kiểm tra lại.\r\n"
        "| Hẹn kiểm tra lúc 09:30 (Nguồn: báo cáo kho) | Mai |\r\n- Gửi báo cáo."
    )
    content["user_text"] = (
        clean.replace("lại.", "lại. (Nguồn: 00:00:19.8, 00:01:16.4)").replace(
            "kho) |", "kho) (Nguồn: 01:05:07.4) |"
        )
        + " [0.0s]"
    )
    first = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    edited = versions.edit_version(meeting_id, first, content)

    saved = versions.read_version(meeting_id, edited)["content"]
    assert render_minutes(saved) == clean
    assert saved["user_text"] == content["user_text"]
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, edited)
    assert clean in markdown
    assert "> Generation: Edited from locally extracted minutes." in markdown
    assert "## Source references" not in markdown
    assert "00:00:00.0–00:00:02.0" not in markdown


def test_offline_draft_edit_and_export_preserve_provenance_and_action_caveat(tmp_path):
    meetings, meeting_id, _run_id = make_meeting_with_run(tmp_path / "meetings")
    versions = MinutesStore(meetings)
    first = OfflineMinutesService(meetings).generate(meeting_id)
    content = copy.deepcopy(versions.read_version(meeting_id, first)["content"])
    assert content["actions"] == []
    content["user_text"] = "# Biên bản đã sửa\n## Việc cần làm\n- Kiểm tra thử nghiệm."
    edited = versions.edit_version(meeting_id, first, content)
    destination = tmp_path / "edited-minutes.md"
    MeetingExportService(meetings).export_minutes(meeting_id, edited, destination)
    exported = destination.read_text(encoding="utf-8")
    manifest = versions.read_version(meeting_id, edited)["manifest"]
    assert manifest["parent_version_id"] == first
    assert manifest["source_origin"] == "extractive"
    assert "> Generation: Edited from locally extracted minutes." in exported
    assert (
        "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        in exported
    )
    assert "## Việc cần làm" in exported


def test_provider_edited_export_labels_origin_and_action_caveat_without_actions(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    first = versions.save_version(meeting_id, run_id, "provider", sample_content(run_id), "prompt")
    content = sample_content(run_id)
    content["user_text"] = "# Revised minutes without actions"
    edited = versions.edit_version(meeting_id, first, content)
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, edited)
    assert "> Generation: Edited from provider-generated minutes." in markdown
    assert (
        "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        in markdown
    )


def test_transcript_export_uses_selected_working_run(tmp_path):
    meetings, meeting_id, earlier = make_meeting_with_run(tmp_path / "meetings")
    transcripts = TranscriptStore(meetings)
    transcripts.save_edits(meeting_id, earlier, {1: "Đã sửa bản ghi trước."})
    later = uuid.uuid4().hex
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    transcripts.save_run(
        meeting_id,
        later,
        model,
        "vi",
        {"duration": 5},
        [{"id": 1, "start": 3.0, "end": 4.5, "text": "Nội dung mới."}],
    )

    service = MeetingExportService(meetings)
    old_text = service.transcript_text(meeting_id, earlier)
    new_text = service.transcript_text(meeting_id, later)
    assert old_text == "[00:00:00.0–00:00:02.0] Đã sửa bản ghi trước.\n"
    assert "Đã thống nhất thử nghiệm." not in old_text
    assert "Nội dung mới." not in old_text
    assert new_text == "[00:00:03.0–00:00:04.5] Nội dung mới.\n"
    assert service.transcript_plain_text(meeting_id, earlier) == "Đã sửa bản ghi trước.\n"
    assert service.transcript_plain_text(meeting_id, later) == "Nội dung mới.\n"
    plain_destination = tmp_path / "transcript-plain.txt"
    assert (
        service.export_transcript_plain(meeting_id, later, plain_destination) == plain_destination
    )
    assert plain_destination.read_text(encoding="utf-8") == "Nội dung mới.\n"


def test_audio_export_copies_original_format_without_modifying_source(tmp_path):
    meetings, meeting_id, _run_id = make_meeting_with_run(tmp_path / "meetings")
    source = meetings._meeting_dir(meeting_id) / "audio.mp3"
    original = b"ID3" + bytes(range(256)) * 8192
    source.write_bytes(original)
    meetings.update_metadata(meeting_id, state="completed", audio_file=source.name)
    service = MeetingExportService(meetings)
    assert service.audio_info(meeting_id) == {
        "fileName": "recording.mp3",
        "extension": "mp3",
    }
    destination = tmp_path / "meeting.mp3"
    assert service.export_audio(meeting_id, None) is None
    assert service.export_audio(meeting_id, destination) == destination
    assert destination.read_bytes() == source.read_bytes() == original
    with pytest.raises(FileExistsError, match="Confirm"):
        service.export_audio(meeting_id, destination)
    assert destination.read_bytes() == original
    with pytest.raises(ValueError, match=".mp3"):
        service.export_audio(meeting_id, tmp_path / "wrong.wav")
    with pytest.raises(ValueError, match="outside fahmm-managed"):
        service.export_audio(meeting_id, meetings.root / meeting_id / "copy.mp3")


def test_export_cancel_overwrite_and_restricted_no_network(tmp_path, monkeypatch):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    version = MinutesStore(meetings).save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    destination = tmp_path / "minutes.md"
    attempts = []
    monkeypatch.setattr(socket.socket, "connect", lambda *args: attempts.append(args))
    service = MeetingExportService(meetings)
    assert service.export_minutes(meeting_id, version, None) is None
    assert not destination.exists()
    assert meetings.privacy_mode(meeting_id) == "restricted"
    assert service.export_minutes(meeting_id, version, destination) == destination
    before = destination.read_bytes()
    assert "Đã thống nhất" in destination.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError, match="Confirm"):
        service.export_minutes(meeting_id, version, destination)
    assert destination.read_bytes() == before
    assert service.export_minutes(meeting_id, version, destination, overwrite=True) == destination
    transcript = tmp_path / "transcript.txt"
    assert service.export_transcript(meeting_id, run_id, transcript) == transcript
    assert transcript.read_text(encoding="utf-8") == (
        "[00:00:00.0–00:00:02.0] Đã thống nhất thử nghiệm.\n"
    )
    assert attempts == []


def test_export_failure_preserves_target_and_removes_temporary(tmp_path, monkeypatch):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    service = MeetingExportService(meetings)
    destination = tmp_path / "transcript.txt"
    destination.write_bytes(b"prior file")

    def fail_replace(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(meeting_export.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk full"):
        service.export_transcript(meeting_id, run_id, destination, overwrite=True)
    assert destination.read_bytes() == b"prior file"
    assert not list(tmp_path.glob(".transcript.txt-*.tmp"))


def test_managed_destination_is_rejected(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    service = MeetingExportService(meetings)
    with pytest.raises(ValueError, match="outside fahmm-managed"):
        service.export_transcript(meeting_id, run_id, meetings.root / meeting_id / "transcript.txt")
    model_root = meetings.root.parent / "models"
    model_root.mkdir()
    with pytest.raises(ValueError, match="outside fahmm-managed"):
        service.export_transcript(meeting_id, run_id, model_root / "transcript.txt")


def test_domain_preview_and_export_use_same_saved_claims_and_freeform_text(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    source = {
        "run_id": run_id,
        "segment_id": 1,
        "start": 0.0,
        "end": 2.0,
        "excerpt": "Đã thống nhất thử nghiệm.",
    }
    content = new_domain_content("project_status", title="Client status")
    content["domain"]["sections"]["actions"] = [
        new_claim(
            "Đã thống nhất thử nghiệm.",
            "extractive",
            sources=[source],
            owner="Chưa rõ",
            due_date="Chưa rõ",
            confirmation_status="suggested",
        )
    ]
    content["domain"]["sections"]["status_updates"] = [
        new_claim("Đã thống nhất thử nghiệm.", "extractive", sources=[source], kind="progress")
    ]
    store = MinutesStore(meetings)
    version_id = store.save_version(meeting_id, run_id, "extractive", content, "default")
    saved = store.read_version(meeting_id, version_id)["content"]
    preview = render_minutes(saved)
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, version_id)
    assert preview in markdown
    assert "Loại cuộc họp: Cập nhật dự án" in preview
    assert "Ngày giờ họp: Chưa rõ" in preview
    assert "- Đã thống nhất thử nghiệm." in preview
    assert "Cần xem lại" not in preview
    assert "## Ghi nhận UAT" not in preview
    assert "## Yêu cầu ứng viên" not in preview
    edited = copy.deepcopy(saved)
    edited["user_text"] = "# Bản đã sửa\nNội dung tự do."
    edited_id = store.edit_version(meeting_id, version_id, edited)
    freeform = MeetingExportService(meetings).minutes_markdown(meeting_id, edited_id)
    assert "Nội dung tự do." in freeform
    assert "## Source references" not in freeform


def test_confirmed_claims_hide_parenthetical_review_details_but_keep_saved_sources(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path / "meetings")
    source = {
        "run_id": run_id,
        "segment_id": 1,
        "start": 0.0,
        "end": 2.0,
        "excerpt": "Đã thống nhất thử nghiệm.",
    }
    content = new_domain_content("general", title="Biên bản")
    summary = new_claim("Đã thống nhất thử nghiệm.", "extractive", sources=[source])
    summary["review_status"] = "confirmed"
    pending = new_claim("Cần kiểm tra thêm.", "extractive", sources=[source])
    action = new_claim(
        "Gửi tài liệu cho khách hàng.",
        "extractive",
        sources=[source],
        owner="Mai",
        due_date="2026-11-20",
        confirmation_status="reviewed",
    )
    action["review_status"] = "confirmed"
    content["domain"]["sections"] = {
        "summary": [summary],
        "topics": [pending],
        "actions": [action],
    }
    version = MinutesStore(meetings).save_version(
        meeting_id, run_id, "extractive", content, "default"
    )
    saved = MinutesStore(meetings).read_version(meeting_id, version)["content"]
    preview = render_minutes(saved)
    assert "- Đã thống nhất thử nghiệm.\n" in preview
    assert "- Đã thống nhất thử nghiệm. (" not in preview
    assert "- Cần kiểm tra thêm.\n" in preview
    assert "| Gửi tài liệu cho khách hàng. | Mai | 2026-11-20 |" in preview
    assert saved["domain"]["sections"]["summary"][0]["sources"] == [source]
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, version)
    assert preview in markdown
    assert "- Đã thống nhất thử nghiệm. (" not in markdown


def test_denso_keeps_claims_in_text_and_only_uses_tables_for_work():
    content = new_domain_content("general", title="Biên bản")
    content["format"] = "denso_warehouse"

    def form_claim(label, text):
        return new_claim(
            text,
            "user",
            label=label,
            method="Chưa rõ",
            data_source="Chưa rõ",
            open_point="Chưa rõ",
            owner="Chưa rõ",
            due_date="Chưa rõ",
        )

    sections = content["domain"]["sections"]
    sections["dashboard_layout"] = [
        form_claim("Màn hình", "Điều chỉnh bố cục."),
        form_claim("Bộ lọc", "Thêm bộ lọc."),
    ]
    sections["sqdcm_kpis"] = [form_claim("Q", "Theo dõi chất lượng.")]
    sections["project_actions"] = [form_claim("Kiểm thử", "Thực hiện kiểm thử.")]
    sections["next_steps"] = [new_claim("Gửi tài liệu.", "user")]
    result = render_minutes(content)
    assert "Điều chỉnh bố cục." in result and "Thêm bộ lọc." in result
    assert "Theo dõi chất lượng." in result and "Thực hiện kiểm thử." in result
    assert "Cách tính / hiển thị: Chưa rõ" in result
    assert "Nguồn dữ liệu: Chưa rõ" in result
    assert "Cần xác nhận: Chưa rõ" in result
    assert result.count("| --- | --- | --- |") == 1
    assert "| Công việc tiếp theo |\n| --- |\n| Gửi tài liệu. |" in result
    sections["sqdcm_kpis"] = []
    sections["next_steps"] = []
    without_optional = render_minutes(content)
    assert "### 4.2. Nhóm chỉ số SQDCM" not in without_optional
    assert "## 8. Công việc tiếp theo" not in without_optional


def test_introductions_and_action_table_preserve_word_block_order():
    from io import BytesIO

    content = new_domain_content("project_status", title="Biên bản")
    content["domain"]["section_introductions"] = {
        "summary": "Đoạn dẫn đầu.\n\nĐoạn dẫn thứ hai.",
        "actions": "Công việc cần theo dõi:",
        "next_steps": "Lời dẫn sau bảng dù chưa có công việc.",
    }
    sections = content["domain"]["sections"]
    sections["summary"] = [new_claim("Nội dung cuộc họp.", "user")]
    sections["actions"] = [new_claim("Gửi báo cáo.", "user", owner="An", due_date="2026-11-30")]
    rejected = new_claim("Không được xuất.", "user")
    rejected["review_status"] = "rejected"
    sections["actions"].append(rejected)
    markdown = render_minutes(content)
    assert "Đoạn dẫn đầu.\n\nĐoạn dẫn thứ hai." in markdown
    assert "| Gửi báo cáo. | An | 2026-11-30 |" in markdown
    assert "Không được xuất." not in markdown
    assert "Lời dẫn sau bảng dù chưa có công việc." in markdown

    with ZipFile(BytesIO(render_docx(markdown))) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    body = root.find("w:body", ns)
    blocks = [
        (
            node.tag.rsplit("}", 1)[-1],
            "".join(item.text or "" for item in node.findall(".//w:t", ns)),
        )
        for node in body
    ]
    first = next(i for i, (_, text) in enumerate(blocks) if "Đoạn dẫn đầu." in text)
    table = next(i for i, (kind, _) in enumerate(blocks) if kind == "tbl")
    last = next(i for i, (_, text) in enumerate(blocks) if "Lời dẫn sau bảng" in text)
    assert first < table < last
    assert "Gửi báo cáo." in blocks[table][1]


def test_denso_keeps_all_summaries_decisions_and_kpi_fields():
    content = new_domain_content("general")
    content["format"] = "denso_warehouse"
    content["domain"]["section_introductions"] = {"sqdcm_kpis": "Văn dẫn KPI tùy chỉnh."}
    sections = content["domain"]["sections"]
    sections["summary"] = [
        new_claim("Tóm tắt thứ nhất.", "user"),
        new_claim("Tóm tắt thứ hai.", "user"),
    ]
    sections["decisions"] = [new_claim("Kết luận một.", "user"), new_claim("Kết luận hai.", "user")]
    sections["sqdcm_kpis"] = [
        new_claim(
            "Chất lượng.",
            "user",
            label="Q",
            method="Tỷ lệ",
            data_source="Báo cáo",
            open_point="Xác nhận kỳ đo",
            owner="Chưa rõ",
            due_date="Chưa rõ",
        )
    ]
    result = render_minutes(content)
    for phrase in (
        "Tóm tắt thứ nhất.",
        "Tóm tắt thứ hai.",
        "Kết luận một.",
        "Kết luận hai.",
        "Văn dẫn KPI tùy chỉnh.",
        "Tỷ lệ",
        "Báo cáo",
        "Xác nhận kỳ đo",
    ):
        assert phrase in result
    assert "| Nhóm |" not in result
    content["user_text"] = "# Bản tự sửa\n\nNguyên văn do người dùng lưu."
    assert render_minutes(content) == content["user_text"]


@pytest.mark.parametrize("denso", [False, True])
def test_work_table_preserves_pipes_and_backslashes_in_markdown_and_word(denso):
    from io import BytesIO

    content = new_domain_content("general")
    task = r"Kiểm tra A|B tại C:\data\report và ký tự \|."
    owner = r"An|Bình\Nhóm"
    if denso:
        content["format"] = "denso_warehouse"
        claim = new_claim(
            task,
            "user",
            label="Chưa rõ",
            method="Chưa rõ",
            data_source="Chưa rõ",
            open_point="Chưa rõ",
            owner=owner,
            due_date="Chưa rõ",
        )
        content["domain"]["sections"]["project_actions"] = [claim]
    else:
        claim = new_claim(task, "user", owner=owner, due_date="Chưa rõ")
        content["domain"]["sections"]["actions"] = [claim]
    markdown = render_minutes(content)
    assert r"A\|B" in markdown
    assert r"C:\\data\\report" in markdown
    assert r"\\\|" in markdown
    with ZipFile(BytesIO(render_docx(markdown))) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    tables = root.findall(".//w:tbl", ns)
    assert any(
        task in [node.text for node in table.findall(".//w:t", ns)]
        and owner in [node.text for node in table.findall(".//w:t", ns)]
        for table in tables
    )


def test_word_table_parser_keeps_escaped_final_pipe_and_unknown_backslash():
    from fahmm.docx_export import _table_row

    assert _table_row(r"| C:\folder | A\|") == [r"C:\folder", "A|"]
    assert _table_row(r"| A\\| B |") == ["A\\", "B"]
