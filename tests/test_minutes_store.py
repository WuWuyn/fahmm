import json
import uuid

import pytest

from fahmm import minutes_store
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


def make_meeting_with_run(tmp_path):
    meetings = MeetingStore(tmp_path)
    meeting_id = meetings.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40,
                           100, tmp_path / "model")
    TranscriptStore(meetings).save_run(
        meeting_id, run_id, model, "vi", {"duration": 3},
        [{"id": 1, "start": 0.0, "end": 2.0, "text": "Đã thống nhất thử nghiệm."}],
    )
    return meetings, meeting_id, run_id


def sample_content(run_id, text="Đã thống nhất thử nghiệm."):
    return {"title": "Chưa rõ", "decisions": [{"text": text, "sources": [
        {"run_id": run_id, "segment_id": 1, "start": 0.0, "end": 2.0}
    ]}]}


def test_versions_approval_edits_and_reopen_preserve_content(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    store = MinutesStore(meetings)
    first = store.save_version(meeting_id, run_id, "extractive", sample_content(run_id), "default")
    store.approve_version(meeting_id, first)
    original = store.read_version(meeting_id, first)
    edited = store.edit_version(meeting_id, first, sample_content(run_id, "User correction"))
    regenerated = store.save_version(meeting_id, run_id, "extractive", sample_content(run_id),
                                     "revised")
    assert len({first, edited, regenerated}) == 3
    assert store.read_version(meeting_id, first) == original
    assert store.read_version(meeting_id, edited)["manifest"]["review_state"] == "unverified"
    assert store.read_version(meeting_id, edited)["content"]["decisions"][0]["text"] == "User correction"
    reopened = MinutesStore(MeetingStore(tmp_path))
    assert reopened.active_version(meeting_id)["manifest"]["version_id"] == regenerated
    assert len(reopened.list_versions(meeting_id)) == 3
    reopened.select_version(meeting_id, first)
    assert reopened.active_version(meeting_id)["manifest"]["review_state"] == "approved"
    assert TranscriptStore(MeetingStore(tmp_path)).active_run(meeting_id)["working"][0]["id"] == 1


def test_invalid_source_and_interrupted_commit_leave_prior_data(tmp_path, monkeypatch):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    store = MinutesStore(meetings)
    first = store.save_version(meeting_id, run_id, "extractive", sample_content(run_id), "default")
    invalid = sample_content(run_id)
    invalid["decisions"][0]["sources"][0]["segment_id"] = 99
    with pytest.raises(ValueError, match="source segment"):
        store.save_version(meeting_id, run_id, "extractive", invalid, "default")

    original_replace = minutes_store.os.replace

    def fail_directory(source, target):
        if str(source).endswith(".tmp"):
            return original_replace(source, target)
        raise OSError("disk full")

    monkeypatch.setattr(minutes_store.os, "replace", fail_directory)
    with pytest.raises(OSError, match="disk full"):
        store.save_version(meeting_id, run_id, "extractive", sample_content(run_id), "default")
    assert store.active_version(meeting_id)["manifest"]["version_id"] == first
    assert len(store.list_versions(meeting_id)) == 1
    assert not list((tmp_path / meeting_id / "minutes").glob(".version-*"))
    metadata = json.loads((tmp_path / meeting_id / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["active_minutes_version"] == first
