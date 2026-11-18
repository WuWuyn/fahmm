import json

from test_cloud_minutes import make_cloud_service

from fahmm.provider_minutes import normalize_domain_provider_minutes, normalize_provider_minutes
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


def test_domain_provider_cannot_confirm_unsupported_customer_facts(tmp_path):
    service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
    TranscriptStore(service.meetings).save_edits(
        meeting_id, run_id, {2: "Nghi do API timeout. Cần làm bản vá; UAT scenario failed."}
    )
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    fake = {
        "sections": {
            "requirements": [
                {
                    "text": "The customer formally approved API v3",
                    "source_ids": [2],
                    "kind": "functional",
                },
                {
                    "text": "API timeout",
                    "source_ids": [2],
                    "kind": "functional",
                    "formality": "user_confirmed",
                },
            ],
            "decisions": [{"text": "Approved rollout", "source_ids": [2]}],
            "incident_findings": [
                {"text": "Nghi do API timeout.", "source_ids": [2], "kind": "confirmed_cause"}
            ],
            "actions": [
                {
                    "text": "Cần làm bản vá",
                    "source_ids": [2],
                    "owner": "Alice",
                    "due_date": "Friday",
                }
            ],
            "uat_observations": [
                {
                    "text": "UAT scenario failed.",
                    "source_ids": [2],
                    "kind": "acceptance",
                    "acceptance_status": "user_confirmed",
                }
            ],
            "topics": [{"text": "Unselected", "source_ids": [3]}],
        }
    }
    content = normalize_domain_provider_minutes(
        fake, snapshot, service.meetings.metadata(meeting_id), "uat_feedback"
    )
    sections = content["domain"]["sections"]
    assert len(sections["requirements"]) == 1
    assert sections["requirements"][0]["formality"] == "candidate"
    assert "decisions" not in sections
    assert sections["incident_findings"][0]["kind"] == "suspected_cause"
    assert sections["actions"][0]["owner"] == "Chưa rõ"
    assert sections["actions"][0]["due_date"] == "Chưa rõ"
    assert sections["uat_observations"][0]["kind"] == "pending_confirmation"
    assert sections["uat_observations"][0]["acceptance_status"] == "pending"
    assert "topics" not in sections
    assert all(
        item["review_status"] == "needs_review" for items in sections.values() for item in items
    )
    service._transport = lambda *_args: fake
    version_id = service.generate(
        snapshot, service.confirm(snapshot, True), meeting_type="uat_feedback"
    )
    saved = service.minutes.read_version(meeting_id, version_id)["content"]
    assert saved["domain"]["meeting_type"] == "uat_feedback"
    assert saved["domain"]["sections"]["requirements"][0]["formality"] == "candidate"
    assert saved["domain"]["sections"]["uat_observations"][0]["acceptance_status"] == "pending"
