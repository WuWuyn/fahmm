import socket

import pytest
from test_minutes_store import make_meeting_with_run

from fahmm.minutes_store import MinutesStore
from fahmm.offline_minutes import UNKNOWN, OfflineMinutesService, extract_minutes
from fahmm.transcripts import TranscriptStore


def test_extracts_explicit_claims_with_source_timestamps_and_unknown_fields():
    meeting = {"name": "Planning", "created_at": "2026-11-14T09:00:00+07:00"}
    segments = [
        {"id": 1, "start": 0.0, "end": 3.0, "text": "Bàn về giao diện tiếng Việt."},
        {"id": 2, "start": 3.0, "end": 7.0, "text": "Chúng ta thống nhất giữ bản thử nghiệm."},
        {"id": 3, "start": 7.0, "end": 10.0, "text": "Cần làm bản nháp tuần này."},
        {"id": 4, "start": 10.0, "end": 13.0, "text": "Ai kiểm tra âm thanh?"},
    ]
    result = extract_minutes(meeting, "a" * 32, segments)
    assert result["title"] == "Planning"
    assert result["date"] == "2026-11-14"
    assert result["attendees"] == UNKNOWN
    assert result["summary"] and result["topics"]
    decision = result["decisions"][0]
    assert "thống nhất" in decision["text"]
    assert decision["sources"] == [{"run_id": "a" * 32, "segment_id": 2, "start": 3.0, "end": 7.0}]
    action = result["actions"][0]
    assert action["owner"] == action["due_date"] == UNKNOWN
    assert action["sources"][0]["segment_id"] == 3
    assert result["open_questions"][0]["sources"][0]["segment_id"] == 4
    assert "extractive" in result["label"]


def test_no_decision_does_not_invent_one_and_uses_edited_text():
    result = extract_minutes(
        {"name": "Untitled meeting", "created_at": "2026-11-14T00:00:00Z"},
        "b" * 32,
        [{"id": 1, "start": 0, "end": 1, "text": "  Đây là bản đã sửa.  "}],
    )
    assert result["title"] == UNKNOWN
    assert result["decisions"] == [{"text": UNKNOWN, "sources": []}]
    assert result["topics"][0]["text"] == "Đây là bản đã sửa."


@pytest.mark.parametrize("segments", [[], [{"id": 1, "start": 0, "end": 1, "text": " "}]])
def test_empty_transcript_rejected_without_draft(segments):
    with pytest.raises(ValueError, match="non-empty transcript"):
        extract_minutes({}, "a" * 32, segments)


def test_template_regeneration_is_offline_and_preserves_approved_version(tmp_path, monkeypatch):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    minutes = MinutesStore(meetings)
    service = OfflineMinutesService(meetings)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)

    def blocked(*_args, **_kwargs):
        raise AssertionError("Offline minutes tried to access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    first = service.generate(meeting_id)
    minutes.approve_version(meeting_id, first)
    approved = minutes.read_version(meeting_id, first)
    template = minutes.read_template(meeting_id)
    template["headings"]["summary"] = "Tóm tắt đã chỉnh"
    template["guidance"] = "Check every statement."
    template["topic_limit"] = 1
    minutes.save_template(meeting_id, template)
    TranscriptStore(meetings).save_edits(meeting_id, run_id, {1: "Đã thống nhất sửa bản nháp."})
    second = service.generate(meeting_id)
    new_content = minutes.read_version(meeting_id, second)["content"]
    assert new_content["headings"]["summary"] == "Tóm tắt đã chỉnh"
    assert len(new_content["topics"]) == 1
    assert "sửa bản nháp" in new_content["decisions"][0]["text"]
    assert minutes.read_version(meeting_id, first) == approved
    assert minutes.read_version(meeting_id, second)["manifest"]["review_state"] == "unverified"
