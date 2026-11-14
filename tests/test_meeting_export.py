"""Saved minutes formatting stays independent of the Qt review widget."""

import socket
import uuid

import pytest
from test_minutes_store import make_meeting_with_run, sample_content

from fahmm import meeting_export
from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.transcripts import TranscriptStore


def test_explicit_minutes_version_review_state_and_vietnamese(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    approved = versions.save_version(meeting_id, run_id, "extractive", sample_content(run_id),
                                     "default")
    versions.approve_version(meeting_id, approved)
    newer = versions.save_version(meeting_id, run_id, "extractive",
                                 sample_content(run_id, "Bản chưa duyệt"), "default")

    service = MeetingExportService(meetings)
    first = service.minutes_markdown(meeting_id, approved)
    second = service.minutes_markdown(meeting_id, newer)
    assert "> Review state: Approved" in first
    assert "Đã thống nhất thử nghiệm." in first
    assert "[0.0s]" in first
    assert "Bản chưa duyệt" not in first
    assert "> Review state: Unverified" in second
    assert "Bản chưa duyệt" in second


def test_edited_minutes_keep_labeled_underlying_sources(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    versions = MinutesStore(meetings)
    content = sample_content(run_id)
    content["user_text"] = "# Biên bản đã sửa\nQuyết định cần kiểm tra lại."
    edited = versions.save_version(meeting_id, run_id, "user_edit", content, "default")

    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, edited)
    assert "# Biên bản đã sửa" in markdown
    assert "## Source references from the underlying draft" in markdown
    assert "do not automatically verify the edited text" in markdown
    assert "00:00:00.0–00:00:02.0" in markdown


def test_transcript_export_uses_selected_working_run(tmp_path):
    meetings, meeting_id, earlier = make_meeting_with_run(tmp_path)
    transcripts = TranscriptStore(meetings)
    transcripts.save_edits(meeting_id, earlier, {1: "Đã sửa bản ghi trước."})
    later = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40,
                           100, tmp_path / "model")
    transcripts.save_run(
        meeting_id, later, model, "vi", {"duration": 5},
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
