"""Meeting deletion cannot escape its app-owned directory."""

import os
import subprocess
import uuid

import pytest
from test_media import make_audio

from fahmm import meeting_deletion
from fahmm.media import import_audio
from fahmm.meeting_deletion import DeletionIncompleteError, MeetingDeletionService
from fahmm.storage import MeetingStore


def test_delete_one_import_preserves_original_export_model_and_other_meeting(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    source = tmp_path / "original.wav"
    make_audio(source)
    original_bytes = source.read_bytes()
    imported = import_audio(store, source)
    other = store.create({})
    export = tmp_path / "minutes.md"
    export.write_text("user-owned copy", encoding="utf-8")
    model = tmp_path / "models" / "model.bin"
    model.parent.mkdir()
    model.write_bytes(b"model")
    meeting_dir = store._meeting_dir(imported)
    (meeting_dir / ".interrupted.tmp").write_bytes(b"temporary")

    MeetingDeletionService(store).delete(imported)

    assert not meeting_dir.exists()
    assert not (store.root / f".deleting-{imported}").exists()
    assert source.read_bytes() == original_bytes
    assert export.read_text(encoding="utf-8") == "user-owned copy"
    assert model.read_bytes() == b"model"
    assert store.metadata(other)["id"] == other


def test_delete_recorded_meeting_removes_audio_and_temporary_chunks(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    recorded = store.create({})
    other = store.create({})
    directory = store._meeting_dir(recorded)
    (directory / "recording.wav").write_bytes(b"recording")
    (directory / "system" / "partial.wav").write_bytes(b"chunk")
    (directory / ".recording-interrupted.tmp").write_bytes(b"temporary")

    MeetingDeletionService(store).delete(recorded)

    assert not directory.exists()
    assert not (store.root / f".deleting-{recorded}").exists()
    assert store.metadata(other)["id"] == other


def test_delete_rejects_invalid_id_and_escaping_link(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting_id = store.create({})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    service = MeetingDeletionService(store)
    with pytest.raises(ValueError, match="Invalid meeting ID"):
        service.delete("../outside")
    link = store._meeting_dir(meeting_id) / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Creating symlinks is unavailable")
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, text=True, check=False,
        )
        if created.returncode:
            pytest.skip("Creating a Windows junction is unavailable")
    try:
        with pytest.raises(ValueError, match="link or reparse"):
            service.delete(meeting_id)
    finally:
        if link.is_junction():
            link.rmdir()
        else:
            link.unlink()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert store._meeting_dir(meeting_id).exists()


def test_reparse_detection_rejects_escape_without_link_privilege(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path / "meetings")
    meeting_id = store.create({})
    entry = store._meeting_dir(meeting_id) / "escape"
    entry.mkdir()
    other = store.create({})
    original = meeting_deletion._is_reparse
    monkeypatch.setattr(meeting_deletion, "_is_reparse", lambda path: (
        path == entry or original(path)
    ))
    with pytest.raises(ValueError, match="link or reparse"):
        MeetingDeletionService(store).delete(meeting_id)
    assert store._meeting_dir(meeting_id).exists()
    assert store.metadata(other)["id"] == other


def test_incomplete_tombstone_is_reported_and_retry_is_scoped(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path / "meetings")
    selected = store.create({})
    other = store.create({})
    service = MeetingDeletionService(store)
    original_remove = meeting_deletion._remove_tree

    def fail_after_one_file(path):
        if path.name == f".deleting-{selected}":
            (path / "metadata.json").unlink()
            raise PermissionError("file is locked")
        return original_remove(path)

    monkeypatch.setattr(meeting_deletion, "_remove_tree", fail_after_one_file)
    with pytest.raises(DeletionIncompleteError, match="pending cleanup"):
        service.delete(selected)
    assert service.incomplete_deletions() == [selected]
    assert not store._meeting_dir(selected).exists()
    assert store.metadata(other)["id"] == other
    monkeypatch.setattr(meeting_deletion, "_remove_tree", original_remove)
    service.retry_cleanup(selected)
    assert service.incomplete_deletions() == []
    assert store.metadata(other)["id"] == other


def test_orphan_import_cleanup_requires_confirmation_and_ignores_live_or_unrelated(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    completed = store.create({})
    orphan = uuid.uuid4().hex
    live = uuid.uuid4().hex
    orphan_stage = store.root / f".import-{orphan}"
    live_stage = store.root / f".import-{live}"
    completed_stage = store.root / f".import-{completed}"
    unrelated = store.root / ".import-not-a-meeting"
    for path in (orphan_stage, live_stage, completed_stage, unrelated):
        path.mkdir()
        (path / "audio.wav").write_bytes(b"partial")
    store.begin_import(live)
    service = MeetingDeletionService(store)
    assert service.orphan_imports() == [orphan]
    assert service.cleanup_orphan_import(orphan, confirmed=False) is False
    assert orphan_stage.exists()
    with pytest.raises(RuntimeError, match="active"):
        service.cleanup_orphan_import(live, confirmed=True)
    assert service.cleanup_orphan_import(orphan, confirmed=True) is True
    assert not orphan_stage.exists()
    assert live_stage.exists() and completed_stage.exists() and unrelated.exists()
    assert store.metadata(completed)["id"] == completed
    store.end_import(live)
