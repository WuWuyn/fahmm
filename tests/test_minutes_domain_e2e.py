"""Synthetic, consent-free IT meeting scenarios exercise the complete local minutes flow."""

import copy
import uuid

import pytest

from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


@pytest.mark.parametrize(
    ("meeting_type", "utterance", "section"),
    [
        ("requirement_gathering", "Khách hàng yêu cầu API xuất CSV.", "requirements"),
        (
            "technical_discussion",
            "Cân nhắc API v2 và phương án B, chưa thống nhất.",
            "technical_considerations",
        ),
        ("project_status", "Tiến độ hoàn thành 70% milestone API.", "status_updates"),
        ("issue_incident", "Nghi do database timeout gây lỗi API.", "incident_findings"),
        ("uat_feedback", "UAT scenario đăng nhập failed.", "uat_observations"),
    ],
)
def test_local_customer_minutes_review_approve_reopen_export(
    tmp_path, meeting_type, utterance, section
):
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
        [{"id": 1, "start": 0.0, "end": 2.0, "text": utterance}],
    )
    store = MinutesStore(meetings)
    draft_id = OfflineMinutesService(meetings).generate(meeting_id, meeting_type=meeting_type)
    draft = store.read_version(meeting_id, draft_id)["content"]
    assert draft["domain"]["sections"][section]
    assert all(not entry["drifted"] for entry in store.source_drift(meeting_id, draft_id))
    for entry in store.source_drift(meeting_id, draft_id):
        assert entry["source"]["excerpt"] == utterance
    revised = copy.deepcopy(draft)
    first_claim = revised["domain"]["sections"]["topics"][0]
    first_claim["text"] += " (đã đối chiếu)"
    first_claim["origin"] = "user_provided"
    for items in revised["domain"]["sections"].values():
        for claim in items:
            claim["review_status"] = "confirmed"
    edited_id = store.edit_domain_version(meeting_id, draft_id, revised)
    store.approve_version(meeting_id, edited_id)
    reopened = MinutesStore(MeetingStore(meetings.root))
    assert reopened.read_version(meeting_id, edited_id)["manifest"]["review_state"] == "approved"
    assert reopened.read_version(meeting_id, draft_id)["manifest"]["review_state"] == "unverified"
    export = MeetingExportService(meetings).minutes_markdown(meeting_id, edited_id)
    assert utterance in export
    assert "(đã đối chiếu)" in export
    assert "Chưa rõ" in export
    assert "assigned or tracked tasks" in export
    sections = revised["domain"]["sections"]
    assert not any(
        item.get("formality") == "user_confirmed" for items in sections.values() for item in items
    )
    assert not any(
        item.get("kind") == "confirmed_cause" for items in sections.values() for item in items
    )
    assert not any(
        item.get("acceptance_status") == "user_confirmed"
        for items in sections.values()
        for item in items
    )
    assert not any("task_id" in item for items in sections.values() for item in items)
    if meeting_type == "technical_discussion":
        assert "decisions" not in sections
