"""Saved minutes formatting stays independent of the Qt review widget."""

import copy
import socket
import uuid

import pytest
from test_minutes_store import make_meeting_with_run, sample_content

from fahmm import meeting_export
from fahmm.meeting_export import MeetingExportService, render_minutes
from fahmm.minutes_domain import new_claim, new_domain_content
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.transcripts import TranscriptStore


def test_explicit_minutes_version_review_state_and_vietnamese(tmp_path):
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
    assert "> Review state: Approved" in first
    assert "> Draft type: Source-linked extractive draft; not a semantic AI summary." in first
    assert "Đã thống nhất thử nghiệm." in first
    assert "[0.0s]" in first
    assert "Bản chưa duyệt" not in first
    assert "> Review state: Unverified" in second
    assert "Bản chưa duyệt" in second


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


def test_edited_minutes_keep_labeled_underlying_sources(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    content = sample_content(run_id)
    content["user_text"] = "# Biên bản đã sửa\nQuyết định cần kiểm tra lại."
    first = versions.save_version(
        meeting_id, run_id, "extractive", sample_content(run_id), "default"
    )
    edited = versions.edit_version(meeting_id, first, content)

    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, edited)
    assert "# Biên bản đã sửa" in markdown
    assert (
        "> Draft type: Edited from an offline extractive draft; user edits have not been automatically verified."
        in markdown
    )
    assert "## Source references from the underlying draft" in markdown
    assert "do not automatically verify the edited text" in markdown
    assert "00:00:00.0–00:00:02.0" in markdown


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
    assert (
        "> Draft type: Edited from an offline extractive draft; user edits have not been automatically verified."
        in exported
    )
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
    assert (
        "> Draft type: Edited from a provider-generated draft; user edits have not been automatically verified."
        in markdown
    )
    assert (
        "> Any action items in these minutes are suggestions, not assigned or tracked tasks."
        in markdown
    )


def test_transcript_export_uses_selected_working_run(tmp_path):
    meetings, meeting_id, earlier = make_meeting_with_run(tmp_path)
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


def test_domain_preview_and_export_use_same_saved_claims_and_freeform_notice(tmp_path):
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
    assert "Ngày giờ họp: Chưa rõ" in preview
    assert "Người phụ trách: Chưa rõ" in preview
    assert "00:00:00.0–00:00:02.0" in preview
    assert "Cần xem lại" in preview
    assert "chưa phải công việc được theo dõi" in preview
    assert "## Ghi nhận UAT" not in preview
    assert "## Yêu cầu ứng viên" not in preview
    edited = copy.deepcopy(saved)
    edited["user_text"] = "# Bản đã sửa\nNội dung tự do."
    edited_id = store.edit_version(meeting_id, version_id, edited)
    freeform = MeetingExportService(meetings).minutes_markdown(meeting_id, edited_id)
    assert "Nội dung tự do." in freeform
    assert "## Source references from the underlying draft" in freeform
    assert "do not automatically verify the edited text" in freeform
