import json
import uuid

import numpy as np
import pytest

from fahmm import transcripts
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


def test_edits_and_reruns_preserve_original_and_prior_work(tmp_path):
    meetings = MeetingStore(tmp_path)
    meeting = meetings.create({"system": "speaker", "microphone": "mic"})
    meetings.write_chunk(meeting, "system", 0, np.ones(1000))
    meetings.finalize(meeting)
    store = TranscriptStore(meetings)
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    first = uuid.uuid4().hex
    source = [{"id": 1, "start": 0.0, "end": 0.8, "text": "helo"}]
    store.save_run(meeting, first, model, "vi", {"detected_language": "vi", "duration": 1}, source)
    store.save_edits(meeting, first, {1: "hello"})
    assert (
        TranscriptStore(MeetingStore(tmp_path)).active_run(meeting)["working"][0]["text"] == "hello"
    )
    assert store.read_run(meeting, first)["original"][0]["text"] == "helo"
    second = uuid.uuid4().hex
    store.save_run(
        meeting,
        second,
        model,
        "auto",
        {"detected_language": "en", "duration": 1},
        [{"id": 1, "start": 0, "end": 1, "text": "new"}],
    )
    assert store.active_run(meeting)["manifest"]["run_id"] == second
    assert store.read_run(meeting, first)["working"][0]["text"] == "hello"
    store.select_run(meeting, first)
    assert store.active_run(meeting)["manifest"]["model_revision"] == "a" * 40
    assert meetings.metadata(meeting)["active_run"] == first


def test_failed_edit_save_does_not_replace_working_copy(tmp_path, monkeypatch):
    meetings = MeetingStore(tmp_path)
    meeting = meetings.create({"system": "speaker", "microphone": "mic"})
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    run_id = uuid.uuid4().hex
    store = TranscriptStore(meetings)
    store.save_run(
        meeting,
        run_id,
        model,
        "vi",
        {"duration": 1},
        [{"id": 1, "start": 0, "end": 1, "text": "old"}],
    )
    path = tmp_path / meeting / "transcripts" / run_id / "working.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    original_replace = transcripts.os.replace

    def fail_working(source, target):
        if target == path:
            raise OSError("disk full")
        return original_replace(source, target)

    monkeypatch.setattr(transcripts.os, "replace", fail_working)
    with pytest.raises(OSError, match="disk full"):
        store.save_edits(meeting, run_id, {1: "new"})
    assert json.loads(path.read_text(encoding="utf-8")) == before
    assert store.read_run(meeting, run_id)["original"] == before
