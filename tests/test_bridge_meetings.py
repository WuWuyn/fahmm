"""The bridge keeps meeting data local and preserves document history."""

import wave

import pytest

from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.models import InstalledModel


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


def test_import_transcript_and_minutes_preserve_history(tmp_path):
    source = tmp_path / "Tiếng Việt.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(48_000)
        audio.writeframes(b"\0\0" * 48_000)
    original_bytes = source.read_bytes()
    app = BridgeApplication(tmp_path / "data")
    call(app, "session.hello", versions=[1])
    meeting = call(app, "meeting.import", nativePath=str(source))["meetingId"]
    assert source.read_bytes() == original_bytes
    detail = call(app, "meeting.detail", meetingId=meeting)["meeting"]
    assert detail["privacy_mode"] == "restricted"
    assert detail["source_kind"] == "imported"
    assert "recording" not in detail
    assert [item["id"] for item in call(app, "meeting.list")["meetings"]] == [meeting]
    assert (
        call(app, "meeting.rename", meetingId=meeting, name="Review")["meeting"]["name"] == "Review"
    )

    run_id = "a" * 32
    model = InstalledModel("b" * 32, "repo/model", "repo", "MIT", "c" * 40, 100, tmp_path)
    app.transcripts.save_run(
        meeting,
        run_id,
        model,
        "vi",
        {"duration": 1.0},
        [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "Xin chào"},
        ],
    )
    assert call(app, "transcript.list", meetingId=meeting)["activeRunId"] == run_id
    call(app, "transcript.saveEdits", meetingId=meeting, runId=run_id, edits={"0": "Chào bạn"})
    run = call(app, "transcript.read", meetingId=meeting, runId=run_id)["run"]
    assert run["original"][0]["text"] == "Xin chào"
    assert run["working"][0]["text"] == "Chào bạn"
    assert call(app, "transcript.select", meetingId=meeting, runId=run_id)["activeRunId"] == run_id

    first = app.minutes.save_version(
        meeting, run_id, "extractive", {"user_text": "Bản gốc"}, "default"
    )
    call(app, "minutes.approve", meetingId=meeting, versionId=first)
    second = call(
        app, "minutes.edit", meetingId=meeting, versionId=first, content={"user_text": "Bản sửa"}
    )["versionId"]
    assert second != first
    assert (
        call(app, "minutes.read", meetingId=meeting, versionId=first)["version"]["manifest"][
            "review_state"
        ]
        == "approved"
    )
    assert (
        call(app, "minutes.read", meetingId=meeting, versionId=first)["version"]["content"][
            "user_text"
        ]
        == "Bản gốc"
    )
    assert (
        call(app, "minutes.read", meetingId=meeting, versionId=second)["version"]["manifest"][
            "review_state"
        ]
        == "unverified"
    )
    assert call(app, "minutes.list", meetingId=meeting)["activeVersionId"] == second
    call(app, "minutes.select", meetingId=meeting, versionId=first)
    assert call(app, "minutes.list", meetingId=meeting)["activeVersionId"] == first
    restarted = BridgeApplication(tmp_path / "data")
    call(restarted, "session.hello", versions=[1])
    reopened = call(restarted, "transcript.read", meetingId=meeting, runId=run_id)["run"]
    assert reopened["original"][0]["text"] == "Xin chào"
    assert reopened["working"][0]["text"] == "Chào bạn"
    assert call(restarted, "minutes.list", meetingId=meeting)["activeVersionId"] == first


def test_bridge_rejects_invalid_ids_and_managed_import(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    with pytest.raises(ValueError):
        call(app, "meeting.detail", meetingId="../../outside")
    with pytest.raises(ValueError):
        call(app, "transcript.read", meetingId="a" * 32, runId="../outside")
    managed = app.store.root / ("a" * 32) / "audio.wav"
    with pytest.raises(ValueError):
        call(app, "meeting.import", nativePath=str(managed))
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("not audio", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported audio format"):
        call(app, "meeting.import", nativePath=str(unsupported))


def test_template_and_cleanup_operations_keep_other_meetings(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    first = app.store.create({"system": "s", "microphone": "m"})
    second = app.store.create({"system": "s", "microphone": "m"})
    template = call(app, "minutes.template", meetingId=first)["template"]
    template["headings"]["title"] = "Tiêu đề mới"
    assert call(app, "minutes.saveTemplate", meetingId=first, template=template)["saved"]
    assert (
        call(app, "minutes.template", meetingId=first)["template"]["headings"]["title"]
        == "Tiêu đề mới"
    )
    assert (
        call(app, "minutes.template", meetingId=second)["template"]["headings"]["title"]
        != "Tiêu đề mới"
    )
    with pytest.raises(ValueError):
        call(app, "minutes.saveTemplate", meetingId=first, template={**template, "topic_limit": 0})
    assert call(app, "meeting.delete", meetingId=first)["deleted"]
    assert [item["id"] for item in call(app, "meeting.list")["meetings"]] == [second]
    orphan = "c" * 32
    stage = app.store.root / f".import-{orphan}"
    stage.mkdir()
    (stage / "partial.wav").write_bytes(b"partial")
    assert call(app, "meeting.cleanupList")["imports"] == [orphan]
    assert call(app, "meeting.cleanImport", meetingId=orphan)["cleaned"]
    assert not stage.exists()
    assert call(app, "meeting.cleanupList") == {"deletions": [], "imports": []}
