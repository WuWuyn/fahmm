import json
import wave

import numpy as np
import pytest

from fahmm.storage import SAMPLE_RATE, MeetingStore


def test_chunk_storage_is_unique_atomic_and_readable(tmp_path):
    store = MeetingStore(tmp_path)
    first = store.create({"system": "speaker", "microphone": "mic"})
    second = store.create({"system": "speaker", "microphone": "mic"})
    assert first != second
    assert store.metadata(first)["schema_version"] == 1
    path = store.write_chunk(first, "system", 0, np.ones(1000, dtype=np.float32) * 0.5)
    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    with wave.open(str(path), "rb") as file:
        assert file.getnframes() == 1000
        assert file.getframerate() == SAMPLE_RATE
    assert store.metadata(second)["state"] == "recording"


def test_mix_keeps_channels_and_compresses_pause(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(meeting, "system", 0, np.full(1000, 0.5))
    store.write_chunk(meeting, "microphone", 0, np.full(1000, -0.5))
    # The second chunk follows immediately in the active timeline; paused time has no frames.
    store.write_chunk(meeting, "system", 1000, np.full(500, 0.25))
    store.write_chunk(meeting, "microphone", 1000, np.full(500, -0.25))
    result = store.finalize(meeting)
    with wave.open(str(result.path), "rb") as file:
        assert file.getnchannels() == 2
        assert file.getnframes() == 1500
        samples = np.frombuffer(file.readframes(1500), dtype="<i2").reshape(-1, 2)
    assert np.all(samples[:1000, 0] > 0)
    assert np.all(samples[:1000, 1] < 0)
    assert np.all(samples[1000:, 0] > 0)
    assert np.all(samples[1000:, 1] < 0)
    assert len(list((tmp_path / meeting / "system").glob("*.wav"))) == 2


def test_recovery_finds_committed_chunks_even_if_metadata_is_stale(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    other = store.create({"system": "speaker", "microphone": "mic"})
    store.write_chunk(meeting, "system", 0, np.ones(1000))
    store.write_chunk(meeting, "microphone", 0, np.ones(1000))
    corrupt = tmp_path / meeting / "system" / "000000002000-aaaaaaaa.wav"
    corrupt.write_bytes(b"broken")
    assert [item["id"] for item in store.incomplete()] == [meeting]
    result = store.finalize(meeting)
    assert str(corrupt) in result.skipped_chunks
    assert store.metadata(meeting)["state"] == "completed"
    assert store.metadata(other)["state"] == "recording"
    assert not store.incomplete()


def test_failed_final_mix_keeps_sources_recoverable(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    chunk = store.write_chunk(meeting, "system", 0, np.ones(1000))
    from fahmm import storage

    original = storage.os.replace

    def fail_final(source, target):
        if str(target).endswith("recording.wav"):
            raise OSError("disk full")
        return original(source, target)

    monkeypatch.setattr(storage.os, "replace", fail_final)
    with pytest.raises(OSError, match="disk full"):
        store.finalize(meeting)
    assert chunk.exists()
    assert store.metadata(meeting)["state"] == "error"
    assert store.incomplete()[0]["id"] == meeting


def test_metadata_is_json_without_meeting_content(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    data = json.loads((tmp_path / meeting / "metadata.json").read_text(encoding="utf-8"))
    assert data["devices"] == {"system": "speaker", "microphone": "mic"}
