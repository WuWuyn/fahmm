"""Waveform data stays bounded and unsupported audio has a managed WAV fallback."""

import wave

import av
import numpy as np

from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.media import import_audio


def call(app, operation, **params):
    reply = app.handle({"v": 1, "kind": "request", "id": "test",
                        "op": operation, "params": params})
    encode_frame(reply)
    return reply["result"]


def test_long_recording_peaks_are_bounded(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    app.store.write_chunk(meeting, "system", 0, np.ones(1000, dtype=np.float32))
    app.store.finalize(meeting)
    path = app.store._meeting_dir(meeting) / "recording.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(48_000)
        audio.writeframes(b"\0\0\0\0" * (48_000 * 65))
    peaks = call(app, "media.peaks", meetingId=meeting, bins=512)
    assert len(peaks["peaks"]) == 512
    assert 64 < peaks["seconds"] < 66
    assert all(0 <= amplitude <= 1 for amplitude in peaks["peaks"])
    assert len(str(peaks)) < 10_000


def test_flac_fallback_preserves_original_and_playback_is_managed(tmp_path):
    source = tmp_path / "input.flac"
    with av.open(str(source), "w") as container:
        stream = container.add_stream("flac", rate=48_000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, 48_000), dtype=np.int16), format="s16", layout="mono"
        )
        frame.sample_rate = 48_000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    original = source.read_bytes()
    app = BridgeApplication(tmp_path / "data")
    call(app, "session.hello", versions=[1])
    meeting = import_audio(app.store, source)
    fallback = call(app, "media.fallback", meetingId=meeting)
    assert fallback["contentType"] == "audio/wav"
    resolved = call(app, "media.resolve", meetingId=meeting, ticket=fallback["ticket"])
    assert resolved["nativePath"].endswith("playback.wav")
    assert source.read_bytes() == original
    assert app.library.audio_path(meeting).suffix == ".flac"
    with wave.open(resolved["nativePath"], "rb") as audio:
        assert audio.getframerate() == 48_000
        assert audio.getnframes() > 0
