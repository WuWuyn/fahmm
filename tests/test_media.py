import hashlib
import socket
import wave

import av
import numpy as np
import pytest

from fahmm.media import import_audio, iter_pcm, probe_audio
from fahmm.storage import MeetingStore


def make_audio(path):
    samples = (np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 10000).astype("<i2")
    if path.suffix == ".wav":
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(samples.tobytes())
        return
    codec = {".mp3": "mp3", ".m4a": "aac", ".flac": "flac"}[path.suffix]
    with av.open(str(path), mode="w") as output:
        stream = output.add_stream(codec, rate=16000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 16000
        resampler = av.AudioResampler(
            format=stream.codec_context.format,
            layout=stream.layout,
            rate=stream.rate,
        )
        for converted in resampler.resample(frame) + resampler.resample(None):
            for packet in stream.encode(converted):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)


@pytest.mark.parametrize("extension", [".wav", ".mp3", ".m4a", ".flac"])
def test_import_preserves_source_and_works_after_source_removed(tmp_path, extension):
    source = tmp_path / f"speech{extension}"
    make_audio(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    store = MeetingStore(tmp_path / "meetings")
    meeting = import_audio(store, source)
    assert hashlib.sha256(source.read_bytes()).digest() == before
    data = store.metadata(meeting)
    assert data["privacy_mode"] == "restricted"
    assert data["source_kind"] == "imported"
    local = store._meeting_dir(meeting) / data["audio_file"]
    source.unlink()
    assert local.exists()
    assert probe_audio(local).seconds > 0.9
    assert list(store.root.glob(".import-*")) == []


def test_bad_imports_leave_no_meeting(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    unsupported = tmp_path / "speech.txt"
    unsupported.write_bytes(b"text")
    with pytest.raises(ValueError, match="Unsupported"):
        import_audio(store, unsupported)
    corrupt = tmp_path / "speech.mp3"
    corrupt.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="decoded"):
        import_audio(store, corrupt)
    assert list(store.root.iterdir()) == []


@pytest.mark.parametrize("extension", [".wav", ".mp3", ".m4a", ".flac"])
def test_local_decoder_seeks_to_source_timestamp_without_network(tmp_path, extension, monkeypatch):
    source = tmp_path / f"speech{extension}"
    make_audio(source)

    def network_forbidden(*args, **kwargs):
        raise AssertionError("Audio playback attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    chunk = next(iter_pcm(source, start_seconds=0.5))
    assert 0.49 <= chunk.start_seconds <= 0.55
    assert len(chunk.data) > 0
