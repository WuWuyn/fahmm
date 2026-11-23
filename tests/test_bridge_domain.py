"""Domain review bridge operations accept only managed meeting/version identifiers."""

import json
import time
import uuid
from pathlib import Path

import pytest
from test_bridge_cloud import call

from fahmm.bridge.protocol import FrameError, validate_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.models import InstalledModel


def test_domain_bridge_type_edit_drift_and_stale_version(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting_id = app.store.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    app.transcripts.save_run(
        meeting_id,
        run_id,
        model,
        "vi",
        {"duration": 2},
        [{"id": 1, "start": 0.0, "end": 1.0, "text": "Cần làm bản nháp."}],
    )
    first = call(
        app,
        "minutes.generateOffline",
        meetingId=meeting_id,
        runId=None,
        meetingType="project_status",
    )["versionId"]
    assert (
        call(app, "minutes.read", meetingId=meeting_id, versionId=first)["version"]["content"][
            "domain"
        ]["meeting_type"]
        == "project_status"
    )
    changed = call(
        app, "minutes.setType", meetingId=meeting_id, versionId=first, meetingType="uat_feedback"
    )["versionId"]
    assert changed != first
    content = call(app, "minutes.read", meetingId=meeting_id, versionId=changed)["version"][
        "content"
    ]
    content["domain"]["metadata"]["objective"] = {
        "value": "Review UAT",
        "provenance": "user_provided",
        "sources": [],
    }
    edited = call(
        app, "minutes.editDomain", meetingId=meeting_id, versionId=changed, content=content
    )["versionId"]
    with pytest.raises(ValueError, match="Select the latest"):
        call(app, "minutes.editDomain", meetingId=meeting_id, versionId=changed, content=content)
    assert call(app, "minutes.sourceDrift", meetingId=meeting_id, versionId=edited)["sources"]
    app.transcripts.save_edits(meeting_id, run_id, {1: "Changed source"})
    drift = call(app, "minutes.sourceDrift", meetingId=meeting_id, versionId=edited)["sources"]
    assert drift[0]["drifted"] is True
    with pytest.raises(ValueError):
        call(app, "minutes.setType", meetingId=meeting_id, versionId=edited, meetingType="unknown")
    with pytest.raises(ValueError):
        call(app, "minutes.sourceDrift", meetingId="../escape", versionId=edited)


def test_domain_bridge_rejects_unknown_params_and_paths():
    frame = {
        "v": 1,
        "kind": "request",
        "id": "test",
        "op": "minutes.sourceDrift",
        "params": {"meetingId": "a" * 32, "versionId": "b" * 32, "nativePath": "C:/outside"},
    }
    with pytest.raises(FrameError, match="INVALID_FRAME"):
        validate_frame(json.dumps(frame))


def test_long_domain_draft_stays_within_bridge_frame_limit(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting_id = app.store.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {
            "id": index,
            "start": float(index),
            "end": float(index + 1),
            "text": f"API v2 discussion item {index}.",
        }
        for index in range(1500)
    ]
    app.transcripts.save_run(meeting_id, run_id, model, "vi", {"duration": 1500}, segments)
    started = time.perf_counter()
    version_id = call(
        app,
        "minutes.generateOffline",
        meetingId=meeting_id,
        runId=run_id,
        meetingType="technical_discussion",
    )["versionId"]
    read = call(app, "minutes.read", meetingId=meeting_id, versionId=version_id)
    drift = call(app, "minutes.sourceDrift", meetingId=meeting_id, versionId=version_id)
    assert len(read["version"]["content"]["domain"]["sections"]["technical_considerations"]) == 100
    assert len(drift["sources"]) == 108
    assert time.perf_counter() - started < 10


def test_one_click_bridge_to_saved_export_uses_working_transcript(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting_id = app.store.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = json.loads(
        (Path(__file__).parent / "fixtures" / "one_click_minutes_hour.json").read_text(
            encoding="utf-8"
        )
    )
    app.transcripts.save_run(meeting_id, run_id, model, "vi", {"duration": 3600}, segments)
    app.transcripts.save_edits(
        meeting_id, run_id, {2: "Quầy bán lẻ cần có chức năng quét mã vạch và in hóa đơn VAT."}
    )
    version_id = call(
        app, "minutes.generateOffline", meetingId=meeting_id, runId=None, meetingType="general"
    )["versionId"]
    saved = call(app, "minutes.read", meetingId=meeting_id, versionId=version_id)["version"]
    sections = saved["content"]["domain"]["sections"]
    assert saved["manifest"]["review_state"] == "unverified"
    assert any("VAT" in item["text"] for item in sections["requirements"])
    assert any("VAT" in item["sources"][0]["excerpt"] for item in sections["requirements"])
    assert call(app, "minutes.list", meetingId=meeting_id)["activeVersionId"] == version_id
    rendered = call(app, "minutes.renderBody", meetingId=meeting_id, versionId=version_id)[
        "markdown"
    ]
    exported = call(app, "export.minutesMarkdown", meetingId=meeting_id, versionId=version_id)[
        "markdown"
    ]
    assert "VAT" in rendered and "VAT" in exported
    assert "## Quyết định" in exported
    assert "Cần xem lại" not in exported
    assert "Review state:" not in exported
    assert any(item["sources"] for items in sections.values() for item in items)
