"""Read-only, bounded retrieval of live checkpoints."""

import json
import uuid

import pytest

from fahmm.live_asr import LiveCheckpoint, LiveConfig
from fahmm.live_asr_view import MAX_PAGE_BYTES, LiveASRView
from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path
from fahmm.storage import MeetingStore


def checkpoint(store, meeting_id):
    config = LiveConfig(meeting_id, uuid.uuid4().hex, uuid.uuid4().hex, "test/base", "revision")
    return config, LiveCheckpoint(store._meeting_dir(meeting_id), config)


def test_live_pages_include_provisional_results_and_stable_cursor(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({})
    config, saved = checkpoint(store, meeting)
    saved.commit_window(
        0,
        100,
        [(5, 15, "first", "system", "candidate"), (70, 120, "second", "microphone", "provisional")],
        {"boundary_review": True},
        [],
    )
    saved.set_state("needs_review")
    saved.close()
    view = LiveASRView(store)
    listing = view.list_runs(meeting)
    assert listing["runs"][0]["runId"] == config.run_id
    assert listing["runs"][0]["provisionalCount"] == 1
    first = view.read_page(meeting, config.run_id, limit=1)
    assert first["items"][0]["text"] == "first" and first["nextCursor"]
    second = view.read_page(meeting, config.run_id, after=first["nextCursor"], limit=1)
    assert second["items"][0]["status"] == "provisional" and second["nextCursor"] is None
    latest = view.read_page(meeting, config.run_id, limit=1, latest=True)
    assert [item["text"] for item in latest["items"]] == ["second"]
    confirmed = view.read_page(meeting, config.run_id, kind="segments")
    assert [item["text"] for item in confirmed["items"]] == ["first"]
    assert len(json.dumps(first, ensure_ascii=False).encode("utf-8")) < MAX_PAGE_BYTES


def test_missing_checkpoint_is_not_created_and_delete_lock_is_respected(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({})
    view = LiveASRView(store)
    assert view.list_runs(meeting) == {"runs": [], "nextCursor": None}
    with pytest.raises(FileNotFoundError):
        view.read_page(meeting, "a" * 32)
    assert not (store._meeting_dir(meeting) / "transcripts").exists()
    lock = SharedFileLock(live_meeting_lock_path(store.root, meeting), shared=False)
    lock.acquire(timeout=0)
    try:
        with pytest.raises(TimeoutError):
            view.list_runs(meeting)
    finally:
        lock.release()


def test_oversized_items_are_rejected_instead_of_silently_truncated(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting = store.create({})
    config, saved = checkpoint(store, meeting)
    saved.commit_window(
        0, 100, [(5, 15, "a" * (MAX_PAGE_BYTES + 1), "system", "candidate")], {}, []
    )
    saved.close()
    with pytest.raises(ValueError, match="oversized"):
        LiveASRView(store).read_page(meeting, config.run_id)
