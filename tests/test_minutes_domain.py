"""Domain versions remain compatible with generic M3 meeting files."""

import copy
import hashlib
import json
import uuid
from pathlib import Path

import pytest

from fahmm import minutes_store
from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_domain import MEETING_TYPES, new_claim, new_domain_content
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

TYPE_SECTION = {
    "general": None,
    "requirement_gathering": ("requirements", {"kind": "functional", "formality": "candidate"}),
    "technical_discussion": ("technical_considerations", {"kind": "architecture"}),
    "project_status": ("status_updates", {"kind": "milestone"}),
    "issue_incident": ("incident_findings", {"kind": "suspected_cause"}),
    "uat_feedback": (
        "uat_observations",
        {"kind": "observed_result", "acceptance_status": "pending"},
    ),
}
SOURCE_TEXT = "Cần kiểm tra API."


def source(run_id):
    return {"run_id": run_id, "segment_id": 1, "start": 0.0, "end": 3.0, "excerpt": SOURCE_TEXT}


@pytest.fixture
def saved_run(tmp_path):
    meetings = MeetingStore(tmp_path)
    meeting_id = meetings.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    TranscriptStore(meetings).save_run(
        meeting_id,
        run_id,
        model,
        "vi",
        {"duration": 4},
        [{"id": 1, "start": 0.0, "end": 3.0, "text": SOURCE_TEXT}],
    )
    return meetings, meeting_id, run_id


@pytest.mark.parametrize("meeting_type", sorted(MEETING_TYPES))
def test_domain_version_round_trips_for_every_meeting_type(saved_run, meeting_type):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content(meeting_type, title="Customer discussion")
    content["domain"]["metadata"]["project_customer"] = {
        "value": "Customer A",
        "provenance": "user_provided",
        "sources": [],
    }
    content["domain"]["sections"]["topics"] = [
        new_claim(
            SOURCE_TEXT,
            "extractive",
            sources=[source(run_id)],
        )
    ]
    typed_section = TYPE_SECTION[meeting_type]
    if typed_section is not None:
        section, fields = typed_section
        content["domain"]["sections"][section] = [
            new_claim(SOURCE_TEXT, "extractive", sources=[source(run_id)], **fields)
        ]
    assert content["domain"]["metadata"]["meeting_datetime"]["value"] is None
    store = MinutesStore(meetings)
    version_id = store.save_version(meeting_id, run_id, "extractive", content, "default")
    assert store.read_version(meeting_id, version_id)["content"] == content
    assert store.read_version(meeting_id, version_id)["manifest"]["review_state"] == "unverified"


@pytest.mark.parametrize("meeting_type", sorted(MEETING_TYPES))
@pytest.mark.parametrize(
    "mutate",
    [
        lambda content: content["domain"].update(meeting_type="sales_call"),
        lambda content: content["domain"]["metadata"].pop("objective"),
        lambda content: content["domain"]["metadata"]["meeting_datetime"].update(
            value="2026-11-17T09:00:00"
        ),
        lambda content: content["domain"]["sections"].update(unknown=[]),
        lambda content: content["domain"]["sections"].update(
            requirements=[
                new_claim("API must work", "extractive", kind="wrong", formality="candidate")
            ]
        ),
        lambda content: content["domain"]["sections"].update(
            actions=[
                new_claim(
                    "Test API",
                    "extractive",
                    owner="",
                    due_date="Chưa rõ",
                    confirmation_status="suggested",
                )
            ]
        ),
    ],
)
def test_invalid_domain_fields_are_rejected_before_saving(saved_run, meeting_type, mutate):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content(meeting_type)
    mutate(content)
    with pytest.raises(ValueError):
        MinutesStore(meetings).save_version(meeting_id, run_id, "extractive", content, "default")
    assert MinutesStore(meetings).list_versions(meeting_id) == []


def test_claim_ids_must_be_unique_across_sections(saved_run):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content()
    claim = new_claim("Review API", "user_provided")
    content["domain"]["sections"] = {"topics": [claim], "next_steps": [copy.deepcopy(claim)]}
    with pytest.raises(ValueError, match="repeated"):
        MinutesStore(meetings).save_version(meeting_id, run_id, "extractive", content, "default")


@pytest.mark.parametrize(
    "change",
    [
        lambda item: item.update(segment_id=99),
        lambda item: item.update(start=0.5),
        lambda item: item.update(end=2.0),
        lambda item: item.pop("excerpt"),
        lambda item: item.update(excerpt="Invented text"),
        lambda item: item.update(run_id=uuid.uuid4().hex),
    ],
)
def test_domain_source_must_match_selected_working_segment(saved_run, change):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content()
    citation = source(run_id)
    change(citation)
    content["domain"]["sections"]["topics"] = [
        new_claim(SOURCE_TEXT, "extractive", sources=[citation])
    ]
    with pytest.raises(ValueError, match="source"):
        MinutesStore(meetings).save_version(meeting_id, run_id, "extractive", content, "default")
    assert MinutesStore(meetings).list_versions(meeting_id) == []


def test_domain_source_snapshots_report_later_transcript_drift(saved_run):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content()
    content["domain"]["sections"]["topics"] = [
        new_claim(SOURCE_TEXT, "extractive", sources=[source(run_id)])
    ]
    store = MinutesStore(meetings)
    version_id = store.save_version(meeting_id, run_id, "extractive", content, "default")
    before = store.read_version(meeting_id, version_id)
    assert store.source_drift(meeting_id, version_id)[0]["drifted"] is False
    TranscriptStore(meetings).save_edits(meeting_id, run_id, {1: "Đã sửa transcript."})
    drift = store.source_drift(meeting_id, version_id)
    assert drift[0]["drifted"] is True
    assert drift[0]["source"]["excerpt"] == SOURCE_TEXT
    assert drift[0]["current_text"] == "Đã sửa transcript."
    assert store.read_version(meeting_id, version_id) == before


def test_approval_requires_review_and_current_evidence(saved_run):
    meetings, meeting_id, run_id = saved_run
    content = new_domain_content()
    claim = new_claim(SOURCE_TEXT, "extractive", sources=[source(run_id)])
    content["domain"]["sections"]["topics"] = [claim]
    store = MinutesStore(meetings)
    draft_id = store.save_version(meeting_id, run_id, "extractive", content, "default")
    with pytest.raises(ValueError, match="Review every"):
        store.approve_version(meeting_id, draft_id)
    revised = copy.deepcopy(content)
    revised["domain"]["sections"]["topics"][0]["review_status"] = "confirmed"
    confirmed_id = store.edit_version(meeting_id, draft_id, revised)
    rejected = copy.deepcopy(revised)
    rejected["domain"]["sections"]["topics"][0]["review_status"] = "rejected"
    rejected_id = store.edit_version(meeting_id, confirmed_id, rejected)
    TranscriptStore(meetings).save_edits(meeting_id, run_id, {1: "New transcript wording"})
    with pytest.raises(ValueError, match="Transcript source changed"):
        store.approve_version(meeting_id, confirmed_id)
    assert store.read_version(meeting_id, confirmed_id)["manifest"]["review_state"] == "unverified"
    store.approve_version(meeting_id, rejected_id)
    assert store.read_version(meeting_id, rejected_id)["manifest"]["review_state"] == "approved"


def test_domain_atomic_failure_preserves_approved_version_other_meeting_and_asr(
    saved_run, monkeypatch
):
    meetings, meeting_id, run_id = saved_run
    store = MinutesStore(meetings)
    content = new_domain_content()
    content["domain"]["sections"]["topics"] = [
        new_claim(SOURCE_TEXT, "extractive", sources=[source(run_id)])
    ]
    first = store.save_version(meeting_id, run_id, "extractive", content, "default")
    content["domain"]["sections"]["topics"][0]["review_status"] = "confirmed"
    approved = store.edit_version(meeting_id, first, content)
    store.approve_version(meeting_id, approved)
    other_meeting = meetings.create({})
    watched = [
        store._version_dir(meeting_id, approved) / "manifest.json",
        store._version_dir(meeting_id, approved) / "content.json",
        meetings._meeting_dir(meeting_id) / "transcripts" / run_id / "original.json",
        meetings._meeting_dir(other_meeting) / "metadata.json",
    ]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in watched]
    original_replace = minutes_store.os.replace

    def fail_commit(source_path, target_path):
        if str(source_path).endswith(".tmp"):
            return original_replace(source_path, target_path)
        raise OSError("simulated disk failure")

    monkeypatch.setattr(minutes_store.os, "replace", fail_commit)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.save_version(meeting_id, run_id, "extractive", content, "default")
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in watched] == hashes
    assert store.active_version(meeting_id)["manifest"]["version_id"] == approved
    assert not list((meetings._meeting_dir(meeting_id) / "minutes").glob(".version-*"))


def test_documented_domain_example_is_a_saved_version(saved_run):
    meetings, meeting_id, run_id = saved_run
    example = Path(__file__).parent / "fixtures" / "domain_minutes_example.json"
    content = json.loads(example.read_text(encoding="utf-8"))
    content["domain"]["sections"]["topics"][0]["sources"][0]["run_id"] = run_id
    store = MinutesStore(meetings)
    version_id = store.save_version(meeting_id, run_id, "extractive", content, "default")
    assert store.read_version(meeting_id, version_id)["content"] == content


def test_new_domain_version_does_not_rewrite_legacy_minutes_or_asr(saved_run):
    meetings, meeting_id, run_id = saved_run
    store = MinutesStore(meetings)
    generic = {
        "title": "Legacy",
        "topics": [
            {
                "text": SOURCE_TEXT,
                "sources": [{"run_id": run_id, "segment_id": 1, "start": 0.0, "end": 3.0}],
            }
        ],
    }
    old_id = store.save_version(meeting_id, run_id, "extractive", generic, "default")
    store.approve_version(meeting_id, old_id)
    old_markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, old_id)
    watched = [
        store._version_dir(meeting_id, old_id) / "manifest.json",
        store._version_dir(meeting_id, old_id) / "content.json",
        meetings._meeting_dir(meeting_id) / "transcripts" / run_id / "original.json",
        meetings._meeting_dir(meeting_id) / "transcripts" / run_id / "working.json",
    ]
    hashes_before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in watched]
    content = new_domain_content("general")
    content["domain"]["sections"]["topics"] = [
        new_claim(SOURCE_TEXT, "extractive", sources=[source(run_id)])
    ]
    store.save_version(meeting_id, run_id, "extractive", content, "default")
    hashes_after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in watched]
    assert hashes_after == hashes_before
    assert MeetingExportService(meetings).minutes_markdown(meeting_id, old_id) == old_markdown
