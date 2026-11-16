"""Provider keys and native export paths stay outside webview results."""

import json
import uuid

import pytest

from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
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


def test_profile_redaction_and_saved_exports(tmp_path):
    app = BridgeApplication(tmp_path / "data")
    credentials = FakeCredentials()
    app.profiles = ProviderProfiles(tmp_path / "data" / "providers.json", credentials)
    call(app, "session.hello", versions=[1])
    saved = call(
        app,
        "provider.save",
        name="Cloud",
        baseUrl="https://example.org/v1",
        modelId="gpt-test",
        timeoutSeconds=30,
        profileId=None,
        apiKey="secret-value",
    )
    profile_id = saved["profile"]["id"]
    assert saved["profile"]["hasKey"]
    assert "secret-value" not in json.dumps(saved)
    assert "secret-value" not in json.dumps(call(app, "provider.list"))
    assert "secret-value" not in app.profiles.path.read_text(encoding="utf-8")

    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    app.transcripts.save_run(
        meeting,
        run_id,
        model,
        "vi",
        {"duration": 1},
        [
            {"id": 1, "start": 0, "end": 1, "text": "Xin chào"},
        ],
    )
    version = app.minutes.save_version(
        meeting, run_id, "extractive", {"user_text": "# Biên bản tiếng Việt"}, "default"
    )
    assert "Xin chào" in call(app, "export.transcriptText", meetingId=meeting, runId=run_id)["text"]
    assert (
        "Biên bản tiếng Việt"
        in call(app, "export.minutesMarkdown", meetingId=meeting, versionId=version)["markdown"]
    )
    destination = tmp_path / "minutes.md"
    destination.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        call(
            app,
            "export.writeMinutes",
            meetingId=meeting,
            versionId=version,
            nativePath=str(destination),
            overwrite=False,
        )
    assert destination.read_text(encoding="utf-8") == "keep"
    exported = call(
        app,
        "export.writeMinutes",
        meetingId=meeting,
        versionId=version,
        nativePath=str(destination),
        overwrite=True,
    )
    assert exported == {"saved": True, "displayName": "minutes.md"}
    assert "Biên bản tiếng Việt" in destination.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        call(
            app,
            "export.writeTranscript",
            meetingId=meeting,
            runId=run_id,
            nativePath=str(app.store.root / "bad.txt"),
            overwrite=True,
        )
    assert call(app, "provider.delete", profileId=profile_id)["deleted"]
    assert credentials.get_key(profile_id) is None
