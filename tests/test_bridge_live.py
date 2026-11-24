"""The experimental live bridge exposes bounded local data and coordinates jobs."""

import threading
import uuid

import pytest

from fahmm.asr_jobs import JobSnapshot
from fahmm.bridge.protocol import encode_frame, validate_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.live_asr import LiveCheckpoint, LiveConfig
from fahmm.live_asr_jobs import LiveASRJobs, LiveJobSnapshot


def call(app, operation, **params):
    frame = {"v": 1, "kind": "request", "id": "test", "op": operation, "params": params}
    request = validate_frame(encode_frame(frame))
    response = app.handle(request)
    return validate_frame(encode_frame(response))["result"]


def app_with_meeting(tmp_path):
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = app.store.create({})
    config = LiveConfig(meeting, uuid.uuid4().hex, uuid.uuid4().hex, "test/base", "revision")
    saved = LiveCheckpoint(app.store._meeting_dir(meeting), config)
    saved.commit_window(0, 100, [(5, 15, "local text", "system", "candidate")], {}, [])
    saved.set_state("needs_review")
    saved.close()
    return app, meeting, config.run_id


def test_live_bridge_pages_and_stale_cancel_are_scoped_to_the_meeting(tmp_path):
    app, meeting, run = app_with_meeting(tmp_path)
    listing = call(app, "live.runs", meetingId=meeting, after="", limit=10)
    assert listing["runs"][0]["runId"] == run
    page = call(
        app,
        "live.read",
        meetingId=meeting,
        runId=run,
        kind="hypotheses",
        after=0,
        limit=10,
        latest=True,
    )
    assert page["items"][0]["text"] == "local text"
    other = app.store.create({})
    with pytest.raises(FileNotFoundError):
        call(
            app,
            "live.read",
            meetingId=other,
            runId=run,
            kind="hypotheses",
            after=0,
            limit=10,
            latest=False,
        )
    app.live_asr._snapshot = LiveJobSnapshot(state="running", meeting_id=meeting, run_id=run)
    app.live_asr._cancel = threading.Event()
    assert not call(app, "live.cancel", meetingId=other, runId=run)["accepted"]
    assert not app.live_asr._cancel.is_set()
    assert call(app, "live.cancel", meetingId=meeting, runId=run)["accepted"]
    assert call(app, "live.status")["state"] == "cancelling"


def test_heavy_jobs_cannot_start_together_in_one_sidecar(tmp_path):
    app, meeting, run = app_with_meeting(tmp_path)
    app.live_asr._snapshot = LiveJobSnapshot(state="running", meeting_id=meeting, run_id=run)
    with pytest.raises(RuntimeError, match="current transcription or AI"):
        call(app, "minutes.generateLocalStart", meetingId=meeting, meetingType="general")
    with pytest.raises(RuntimeError, match="current transcription or AI"):
        call(app, "asr.start", meetingId=meeting, modelId="b" * 32, language="vi")
    app.live_asr._snapshot = LiveJobSnapshot()
    app.asr._snapshot = JobSnapshot("running", meeting, run, 0.5, 2, None)
    with pytest.raises(RuntimeError, match="current transcription or AI"):
        call(app, "live.start", meetingId=meeting, modelId="b" * 32, language="vi")
    app.asr._snapshot = JobSnapshot("idle", None, None, None, 0, None)
    app.local_minutes._generation["state"] = "running"
    with pytest.raises(RuntimeError, match="current transcription or AI"):
        call(app, "live.resume", meetingId=meeting, runId=run)


def test_live_job_can_start_and_finish_through_the_bridge(tmp_path):
    import numpy as np
    from test_live_asr_jobs import ModelProbe, RecorderProbe, live_worker_fixture, wait_until

    app = BridgeApplication(tmp_path / "data")
    call(app, "session.hello", versions=[1])
    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    for source in ("system", "microphone"):
        app.store.write_chunk(meeting, source, 0, np.full(1000, 0.3, np.float32))
    recorder, models = RecorderProbe(app.store), ModelProbe(tmp_path)
    app.live_asr = LiveASRJobs(
        app.store, models, recorder, worker_target=live_worker_fixture, poll_interval=0.05
    )
    run = call(app, "live.start", meetingId=meeting, modelId=models.model.id, language="vi")[
        "runId"
    ]
    try:
        wait_until(lambda: call(app, "live.status")["state"] == "running")
        recorder.state = "closed"
        wait_until(lambda: call(app, "live.status")["state"] == "completed")
        assert (
            call(app, "live.runs", meetingId=meeting, after="", limit=10)["runs"][0]["runId"] == run
        )
    finally:
        app.live_asr.cancel(meeting, run)
        app.live_asr.wait(5)
