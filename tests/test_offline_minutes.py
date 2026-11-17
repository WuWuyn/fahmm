import socket
import time

import pytest
from test_minutes_store import make_meeting_with_run

from fahmm.minutes_store import MinutesStore
from fahmm.offline_minutes import (
    UNKNOWN,
    OfflineMinutesService,
    extract_domain_minutes,
    extract_minutes,
)
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


@pytest.mark.parametrize(
    ("meeting_type", "text", "section", "kind"),
    [
        ("requirement_gathering", "Khách hàng yêu cầu API xuất CSV.", "requirements", "functional"),
        (
            "technical_discussion",
            "Cân nhắc tích hợp API v2.",
            "technical_considerations",
            "api_integration",
        ),
        ("project_status", "Mốc milestone chưa hoàn thành.", "status_updates", "milestone"),
        (
            "issue_incident",
            "Nghi do database timeout gây lỗi.",
            "incident_findings",
            "suspected_cause",
        ),
        ("uat_feedback", "UAT scenario 1 failed.", "uat_observations", "defect"),
    ],
)
def test_domain_offline_candidates_are_cited_and_unverified(meeting_type, text, section, kind):
    content = extract_domain_minutes(
        {"name": "Client A", "created_at": "2026-11-17T09:00:00+07:00"},
        "a" * 32,
        [{"id": 1, "start": 0.0, "end": 2.0, "text": text}],
        meeting_type,
    )
    domain = content["domain"]
    assert domain["metadata"]["meeting_datetime"]["value"] is None
    item = domain["sections"][section][0]
    assert item["text"] == text
    assert item["kind"] == kind
    assert item["sources"][0]["excerpt"] == text
    assert item["review_status"] == "needs_review"
    assert item["origin"] == "extractive"


def test_domain_alternatives_do_not_become_decisions_and_cause_is_not_confirmed():
    segments = [
        {"id": 1, "start": 0, "end": 2, "text": "Đề xuất phương án API A, chưa thống nhất."},
        {"id": 2, "start": 2, "end": 4, "text": "Nghi do database timeout."},
    ]
    technical = extract_domain_minutes({}, "a" * 32, segments, "technical_discussion")
    assert "decisions" not in technical["domain"]["sections"]
    assert technical["domain"]["sections"]["proposed_solutions"]
    incident = extract_domain_minutes({}, "a" * 32, segments, "issue_incident")
    assert {item["kind"] for item in incident["domain"]["sections"]["incident_findings"]} == {
        "suspected_cause"
    }


def test_domain_uat_failure_is_not_acceptance_and_action_has_no_task_state():
    segments = [
        {"id": 1, "start": 0, "end": 2, "text": "UAT scenario đăng nhập failed."},
        {"id": 2, "start": 2, "end": 4, "text": "Cần làm bản sửa API."},
    ]
    content = extract_domain_minutes({}, "a" * 32, segments, "uat_feedback")
    sections = content["domain"]["sections"]
    assert sections["uat_observations"][0]["acceptance_status"] == "pending"
    assert sections["actions"][0]["owner"] == sections["actions"][0]["due_date"] == UNKNOWN
    assert sections["actions"][0]["confirmation_status"] == "suggested"
    assert "task_id" not in sections["actions"][0]
    assert "assigned" not in sections["actions"][0]


def test_domain_generation_saves_locally_with_network_blocked(tmp_path, monkeypatch):
    meetings, meeting_id, _run_id = make_meeting_with_run(tmp_path)

    def blocked(*_args, **_kwargs):
        raise AssertionError("Offline minutes tried to access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    version_id = OfflineMinutesService(meetings).generate(
        meeting_id, meeting_type="requirement_gathering"
    )
    saved = MinutesStore(meetings).read_version(meeting_id, version_id)
    assert saved["content"]["domain"]["meeting_type"] == "requirement_gathering"


def test_representative_long_domain_transcript_remains_bounded():
    segments = [
        {
            "id": index,
            "start": float(index),
            "end": float(index + 1),
            "text": f"Thảo luận API v2 mục {index}.",
        }
        for index in range(1500)
    ]
    started = time.perf_counter()
    content = extract_domain_minutes({}, "a" * 32, segments, "technical_discussion")
    assert len(content["domain"]["sections"]["technical_considerations"]) == 100
    assert time.perf_counter() - started < 10


def test_domain_excerpt_keeps_exact_working_text_whitespace():
    content = extract_domain_minutes(
        {},
        "a" * 32,
        [{"id": 1, "start": 0, "end": 1, "text": "  API v2  "}],
        "technical_discussion",
    )
    claim = content["domain"]["sections"]["topics"][0]
    assert claim["text"] == "API v2"
    assert claim["sources"][0]["excerpt"] == "  API v2  "
