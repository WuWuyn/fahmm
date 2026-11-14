"""Media tickets cannot cross meeting boundaries or outlive expiry."""

import numpy as np
import pytest

from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication


def call(app, operation, **params):
    reply = app.handle({"v": 1, "kind": "request", "id": "test",
                        "op": operation, "params": params})
    encode_frame(reply)
    return reply["result"]


def make_meeting(app):
    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    app.store.write_chunk(meeting, "system", 0, np.ones(1000, dtype=np.float32))
    app.store.finalize(meeting)
    return meeting


def test_media_ticket_meeting_binding_expiry_and_traversal(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    first = make_meeting(app)
    second = make_meeting(app)
    ticket = call(app, "media.ticket", meetingId=first)["ticket"]
    result = call(app, "media.resolve", meetingId=first, ticket=ticket)
    assert result["contentType"] == "audio/wav"
    assert result["size"] > 0
    assert str(tmp_path) in result["nativePath"]
    with pytest.raises(PermissionError):
        call(app, "media.resolve", meetingId=second, ticket=ticket)
    with pytest.raises(ValueError):
        call(app, "media.ticket", meetingId="../outside")
    expired = call(app, "media.ticket", meetingId=first)["ticket"]
    meeting, path, _ = app._media_tickets[expired]
    app._media_tickets[expired] = (meeting, path, 0)
    with pytest.raises(PermissionError):
        call(app, "media.resolve", meetingId=first, ticket=expired)


def test_media_rejects_symlink_outside_meeting(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = make_meeting(app)
    audio = app.store._meeting_dir(meeting) / "recording.wav"
    outside = tmp_path / "outside.wav"
    outside.write_bytes(audio.read_bytes())
    audio.unlink()
    try:
        audio.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires a Windows privilege on this machine")
    with pytest.raises(ValueError, match="inside"):
        call(app, "media.ticket", meetingId=meeting)


def test_media_rejects_metadata_traversal(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = make_meeting(app)
    app.store.update_metadata(meeting, audio_file="../outside.wav")
    with pytest.raises(ValueError, match="Invalid meeting audio path"):
        call(app, "media.ticket", meetingId=meeting)
