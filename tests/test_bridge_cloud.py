"""Cloud disclosure is held and consumed inside the Python sidecar."""

import socket
import uuid

import pytest

from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.cloud_minutes import CloudMinutesService
from fahmm.models import InstalledModel
from fahmm.providers import ProviderProfiles


class FakeCredentials:
    def __init__(self):
        self.keys = {}

    def set_key(self, profile_id, key):
        self.keys[profile_id] = key

    def get_key(self, profile_id):
        return self.keys.get(profile_id)

    def delete_key(self, profile_id):
        self.keys.pop(profile_id, None)


def call(app, operation, **params):
    reply = app.handle(
        {
            "v": 1,
            "kind": "request",
            "id": "test",
            "op": operation,
            "params": params,
        }
    )
    encode_frame(reply)
    assert reply["kind"] == "response"
    return reply["result"]


def test_restricted_offline_cancel_and_fresh_confirmation(tmp_path, monkeypatch):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    app.transcripts.save_run(
        meeting,
        run_id,
        model,
        "vi",
        {"duration": 2},
        [
            {"id": 1, "start": 0, "end": 1, "text": "Thống nhất thử nghiệm"},
            {"id": 2, "start": 1, "end": 2, "text": "Private detail"},
        ],
    )
    credentials = FakeCredentials()
    app.profiles = ProviderProfiles(tmp_path / "providers.json", credentials)
    profile = app.profiles.save(
        "Provider", "https://example.org/v1", "model", 30, api_key="secret-key"
    )
    sends = []
    app.cloud_minutes = CloudMinutesService(
        app.store,
        app.profiles,
        transport=lambda snapshot, key: sends.append((snapshot.digest, key)) or "# Bản nháp",
    )

    def blocked_socket(*args, **kwargs):
        raise AssertionError("Restricted flow opened a socket")

    monkeypatch.setattr(socket.socket, "connect", blocked_socket)
    offline = call(app, "minutes.generateOffline", meetingId=meeting, runId=None)
    assert (
        app.minutes.read_version(meeting, offline["versionId"])["manifest"]["review_state"]
        == "unverified"
    )
    preview_params = {
        "meetingId": meeting,
        "profileId": profile.id,
        "selectedIds": [1],
        "reviewedIds": [1],
        "prompt": "Viết biên bản",
        "maxTokens": 500,
    }
    with pytest.raises(PermissionError):
        call(app, "cloud.preview", **preview_params)
    assert sends == []

    call(app, "meeting.privacy", meetingId=meeting, mode="cloud_permitted")
    first = call(app, "cloud.preview", **preview_params)
    assert first["preview"]["destination_hostname"] == "example.org"
    assert "Private detail" not in str(first["preview"])
    assert "secret-key" not in str(first["preview"])
    assert call(app, "cloud.cancel", previewId=first["previewId"])["cancelled"]
    with pytest.raises(PermissionError):
        call(app, "cloud.send", previewId=first["previewId"])
    assert sends == []

    second = call(app, "cloud.preview", **preview_params)
    assert call(app, "cloud.confirm", previewId=second["previewId"], accepted=False) == {
        "confirmed": False
    }
    with pytest.raises(PermissionError):
        call(app, "cloud.send", previewId=second["previewId"])
    third = call(app, "cloud.preview", **preview_params)
    assert call(app, "cloud.confirm", previewId=third["previewId"], accepted=True) == {
        "confirmed": True
    }
    version = call(app, "cloud.send", previewId=third["previewId"])["versionId"]
    assert app.minutes.read_version(meeting, version)["manifest"]["review_state"] == "unverified"
    assert len(sends) == 1 and sends[0][1] == "secret-key"
    with pytest.raises(PermissionError):
        call(app, "cloud.send", previewId=third["previewId"])
    fourth = call(app, "cloud.preview", **preview_params)
    with pytest.raises(PermissionError):
        call(app, "cloud.send", previewId=fourth["previewId"])
    assert len(sends) == 1
