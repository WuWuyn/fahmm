"""Bridge job operations keep model paths private and saved transcripts intact."""

import os
import time
import uuid

import numpy as np

from fahmm.asr_jobs import ASRJobController
from fahmm.bridge.protocol import encode_frame
from fahmm.bridge.server import BridgeApplication
from fahmm.models import InstalledModel


def quick_worker(audio, model, language, output, cancel):
    output.put({"type": "started", "info": {"duration": 1, "language": language}})
    output.put(
        {
            "type": "segment",
            "segment": {
                "id": 1,
                "start": 0,
                "end": 1,
                "text": "Xin chào",
            },
        }
    )
    output.put({"type": "completed"})


def crashed_worker(audio, model, language, output, cancel):
    os._exit(7)


def hanging_worker(audio, model, language, output, cancel):
    output.put({"type": "started", "info": {"duration": 100, "language": language}})
    time.sleep(30)


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


def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr("fahmm.models.validate_model_dir", lambda path: None)
    app = BridgeApplication(tmp_path)
    call(app, "session.hello", versions=[1])
    meeting = app.store.create({"system": "speaker", "microphone": "mic"})
    app.store.write_chunk(meeting, "system", 0, np.ones(1000, dtype=np.float32))
    app.store.finalize(meeting)
    model_id = uuid.uuid4().hex
    model_path = app.models._path(model_id)
    model_path.mkdir(parents=True)
    model = InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 10, model_path)
    app.models._register(model)
    return app, meeting, model


def test_offline_model_selection_install_progress_and_delete(tmp_path, monkeypatch):
    app, _, model = prepared(tmp_path, monkeypatch)
    catalog = call(app, "model.catalog")
    assert catalog["selectedId"] == model.id
    assert "path" not in catalog["installed"][0]
    assert call(app, "model.select", modelId=model.id)["selectedId"] == model.id

    def fake_download(repository, *, progress):
        assert repository == "Systran/faster-whisper-base"
        progress("Downloading", 20, 10)
        return model

    monkeypatch.setattr(app.models, "download", fake_download)
    job_id = call(app, "model.install", repository="Systran/faster-whisper-base")["jobId"]
    app.model_jobs.wait()
    status = call(app, "model.installStatus")
    assert status["jobId"] == job_id
    assert status["state"] == "completed" and status["progress"] == 1.0
    assert call(app, "model.delete", modelId=model.id)["deleted"]
    assert not model.path.exists()


def test_asr_cancel_retry_and_prior_active_transcript(tmp_path, monkeypatch):
    app, meeting, model = prepared(tmp_path, monkeypatch)
    prior = uuid.uuid4().hex
    app.transcripts.save_run(
        meeting,
        prior,
        model,
        "vi",
        {"duration": 1},
        [
            {"id": 2, "start": 0, "end": 1, "text": "Prior result"},
        ],
    )
    app.asr = ASRJobController(app.store, app.models, worker_target=hanging_worker)
    call(app, "asr.start", meetingId=meeting, modelId=model.id, language="vi")
    call(app, "asr.cancel")
    app.asr.wait(8)
    assert call(app, "asr.status")["state"] == "cancelled"
    assert call(app, "transcript.list", meetingId=meeting)["activeRunId"] == prior

    app.asr.worker_target = crashed_worker
    call(app, "asr.retry")
    app.asr.wait(10)
    assert call(app, "asr.status")["state"] == "error"
    assert call(app, "transcript.list", meetingId=meeting)["activeRunId"] == prior

    app.asr.worker_target = quick_worker
    run_id = call(app, "asr.retry")["runId"]
    app.asr.wait(10)
    assert call(app, "asr.status")["state"] == "completed"
    assert call(app, "transcript.list", meetingId=meeting)["activeRunId"] == run_id
    assert (
        call(app, "transcript.read", meetingId=meeting, runId=prior)["run"]["original"][0]["text"]
        == "Prior result"
    )
