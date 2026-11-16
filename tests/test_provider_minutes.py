import json

from test_cloud_minutes import make_cloud_service

from fahmm.provider_minutes import normalize_provider_minutes
from fahmm.transcripts import TranscriptStore


def test_plain_text_provider_response_is_saved_unverified(tmp_path):
    service, meeting_id, profile_id, _, _ = make_cloud_service(tmp_path)
    service._transport = lambda *_args: "# Biên bản\nBản nháp cần kiểm tra nguồn."
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    version_id = service.generate(snapshot, service.confirm(snapshot, True))
    version = service.minutes.read_version(meeting_id, version_id)
    assert version["manifest"]["review_state"] == "unverified"
    assert version["manifest"]["origin"] == "provider"
    assert "Bản nháp" in version["content"]["summary"][0]["text"]
    assert version["content"]["summary"][0]["needs_review"]
    assert version["content"]["decisions"][0]["text"] == "Chưa rõ"
    assert version["content"]["attendees"] == "Chưa rõ"


def test_structured_response_validates_citations_and_unknown_action_fields(tmp_path):
    service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
    TranscriptStore(service.meetings).save_edits(
        meeting_id, run_id, {2: "Chúng ta thống nhất thử nghiệm. Cần làm bản nháp."}
    )
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    structured = {
        "summary": [{"text": "Tóm tắt", "source_ids": [2]}],
        "decisions": [
            {"text": "Thử nghiệm", "source_ids": [2]},
            {"text": "Unsupported claim", "source_ids": [99]},
        ],
        "actions": [
            {"task": "Làm bản nháp", "owner": "Alice", "due_date": "tomorrow", "source_ids": [2]}
        ],
    }
    content = normalize_provider_minutes(
        json.dumps(structured), snapshot, service.meetings.metadata(meeting_id)
    )
    assert content["decisions"][0]["sources"][0]["segment_id"] == 2
    assert content["decisions"][0]["sources"][0]["end"] == 2.0
    assert content["decisions"][1]["sources"] == []
    assert content["decisions"][1]["needs_review"]
    assert content["actions"][0]["owner"] == "Chưa rõ"
    assert content["actions"][0]["due_date"] == "Chưa rõ"
    service._transport = lambda *_args: structured
    version_id = service.generate(snapshot, service.confirm(snapshot, True))
    assert service.minutes.read_version(meeting_id, version_id)["content"] == content
