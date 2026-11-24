import io
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
    assert store.metadata(first)["schema_version"] == 2
    assert store.metadata(first)["privacy_mode"] == "restricted"
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


def test_recovery_mix_matches_reference_with_nested_overlaps_and_skipped_chunks(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    other = store.create({"system": "speaker", "microphone": "mic"})
    other_chunk = store.write_chunk(other, "microphone", 0, np.full(128, 0.65))
    other_before = other_chunk.read_bytes()

    def chunk(source, start, frames, value, suffix):
        original = store.write_chunk(meeting, source, start, np.full(frames, value))
        original.replace(original.with_name(f"{start:012d}-{suffix}.wav"))

    chunk("system", 0, 4 * SAMPLE_RATE, 0.1, "00000001")
    chunk("system", SAMPLE_RATE // 4, SAMPLE_RATE // 2, 0.2, "00000002")
    chunk("system", SAMPLE_RATE // 2, 2 * SAMPLE_RATE, 0.3, "00000003")
    # Two chunks start together; the lexically later name wins at each sample.
    chunk("system", SAMPLE_RATE, SAMPLE_RATE // 3, 0.4, "00000004")
    chunk("system", SAMPLE_RATE, SAMPLE_RATE // 4, 0.5, "00000005")
    chunk("system", 6 * SAMPLE_RATE, SAMPLE_RATE // 3, -0.3, "00000006")
    chunk("microphone", 100, SAMPLE_RATE, -0.2, "00000007")
    chunk("microphone", SAMPLE_RATE // 2, 3 * SAMPLE_RATE, -0.4, "00000008")
    chunk("microphone", 5 * SAMPLE_RATE, SAMPLE_RATE // 2, 0.25, "00000009")

    directory = store._meeting_dir(meeting)
    broken = directory / "system" / "000000010000-aaaaaaaa.wav"
    broken.write_bytes(b"broken")
    truncated = directory / "microphone" / "000000020000-bbbbbbbb.wav"
    with wave.open(str(truncated), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(SAMPLE_RATE)
        file.writeframes(b"\0\0" * 20)
    with truncated.open("r+b") as file:
        file.truncate(truncated.stat().st_size - 10)

    scanned, skipped = store.scan_chunks(meeting)
    total = max(item.start_frame + item.frames for items in scanned.values() for item in items)
    expected = np.zeros((total, 2), dtype="<i2")
    # Independently render the whole timeline: ordered chunks overwrite in-place.
    for channel, source in enumerate(("system", "microphone")):
        for item in scanned[source]:
            with wave.open(str(item.path), "rb") as file:
                raw = file.readframes(item.frames)
            expected[item.start_frame : item.start_frame + item.frames, channel] = np.frombuffer(
                raw, dtype="<i2"
            )
    reference = io.BytesIO()
    with wave.open(reference, "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(SAMPLE_RATE)
        file.writeframes(expected.tobytes())

    store.set_state(meeting, "error")
    assert meeting in [item["id"] for item in store.incomplete()]
    result = store.finalize(meeting)
    assert result.path.read_bytes() == reference.getvalue()
    assert set(result.skipped_chunks) == set(skipped) == {str(broken), str(truncated)}
    assert store.metadata(meeting)["state"] == "completed"
    assert other_chunk.read_bytes() == other_before
    assert store.metadata(other)["state"] == "recording"


def test_finalize_does_not_rescan_old_chunks_for_each_output_block(tmp_path, monkeypatch):
    store = MeetingStore(tmp_path)
    meeting = store.create({})
    count = 25
    for index in range(count):
        store.write_chunk(meeting, "system", 2 * index * SAMPLE_RATE, np.array([0.25]))
    chunks, skipped = store.scan_chunks(meeting)
    reads = 0

    class CountedChunk:
        def __init__(self, chunk):
            self.chunk = chunk
            self.path = chunk.path

        @property
        def start_frame(self):
            nonlocal reads
            reads += 1
            return self.chunk.start_frame

        @property
        def frames(self):
            nonlocal reads
            reads += 1
            return self.chunk.frames

    measured = {source: [CountedChunk(item) for item in items] for source, items in chunks.items()}
    monkeypatch.setattr(store, "scan_chunks", lambda _meeting: (measured, skipped))
    result = store.finalize(meeting)
    assert result.path.is_file()
    # A full scan would inspect 25 chunks on each of 49 output blocks.
    assert reads < 40 * count


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


def test_legacy_metadata_is_restricted_and_migrates_with_backup(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({"system": "speaker", "microphone": "mic"})
    metadata_path = tmp_path / meeting / "metadata.json"
    legacy = {
        "schema_version": 1,
        "id": meeting,
        "created_at": "2026-01-01T00:00:00+00:00",
        "state": "recording",
        "devices": {"system": "speaker", "microphone": "mic"},
    }
    metadata_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert store.metadata(meeting)["privacy_mode"] == "restricted"
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == legacy
    store.write_chunk(meeting, "system", 0, np.ones(1000))
    assert store.incomplete()[0]["id"] == meeting
    result = store.finalize(meeting)
    assert result.path.exists()
    assert store.metadata(meeting)["state"] == "completed"
    assert store.metadata(meeting)["schema_version"] == 2
    backup = tmp_path / meeting / "metadata.v1.json"
    assert json.loads(backup.read_text(encoding="utf-8")) == legacy


def test_privacy_mode_validation_and_persistence(tmp_path):
    store = MeetingStore(tmp_path)
    meeting = store.create({})
    assert store.privacy_mode(meeting) == "restricted"
    store.set_privacy_mode(meeting, "cloud_permitted")
    assert MeetingStore(tmp_path).privacy_mode(meeting) == "cloud_permitted"
    store.update_metadata(meeting, processing_state="failed")
    assert MeetingStore(tmp_path).privacy_mode(meeting) == "cloud_permitted"
    with pytest.raises(ValueError, match="privacy mode"):
        store.set_privacy_mode(meeting, "public")
    assert store.privacy_mode(meeting) == "cloud_permitted"
    store.set_privacy_mode(meeting, "restricted")
    assert MeetingStore(tmp_path).privacy_mode(meeting) == "restricted"


@pytest.mark.parametrize("bad_mode", [None, "public", 12, ""])
def test_missing_or_invalid_v2_privacy_mode_fails_closed(tmp_path, bad_mode):
    store = MeetingStore(tmp_path)
    meeting = store.create({})
    path = tmp_path / meeting / "metadata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if bad_mode is None:
        data.pop("privacy_mode")
    else:
        data["privacy_mode"] = bad_mode
    path.write_text(json.dumps(data), encoding="utf-8")
    assert MeetingStore(tmp_path).privacy_mode(meeting) == "restricted"
    assert json.loads(path.read_text(encoding="utf-8")) == data
