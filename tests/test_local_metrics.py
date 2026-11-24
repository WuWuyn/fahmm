"""Measure local AI requests without persisting meeting content."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_local_minutes_checkpoint import BlockingOllama, ChunkClient, wait_terminal
from test_minutes_store import make_meeting_with_run

from fahmm.local_llm import DEFAULT_MODEL, LocalMinutesJobs, OllamaClient, OllamaOutputLimitError


def _metrics_path(store, meeting_id, job_id):
    return store._meeting_dir(meeting_id) / "minutes" / "ai-metrics" / f"{job_id}.json"


class MetricsOllama(BaseHTTPRequestHandler):
    calls = 0

    def do_GET(self):
        body = json.dumps(
            {"models": [{"name": DEFAULT_MODEL, "size": 1, "digest": "a" * 64}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        type(self).calls += 1
        if type(self).calls == 1:
            event = {"message": {"content": "{"}, "done": True, "done_reason": "length"}
        else:
            content = {
                "summary": "Nhóm đã thống nhất phạm vi triển khai trong cuộc họp.",
                "source_ids": [1],
                "items": [],
            }
            event = {
                "message": {"content": json.dumps(content)},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 321,
                "prompt_eval_cached_count": 21,
                "eval_count": 123,
                "total_duration": 2000,
                "load_duration": 100,
                "prompt_eval_duration": 400,
                "eval_duration": 1500,
            }
        body = (json.dumps(event) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def _server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_real_http_attempts_retry_and_unknown_server_values_are_recorded(tmp_path):
    MetricsOllama.calls = 0
    server, thread = _server(MetricsOllama)
    store, meeting_id, run_id = make_meeting_with_run(tmp_path)
    secret = "PRIVATE_MEETING_TEXT_92817"
    from fahmm.transcripts import TranscriptStore

    TranscriptStore(store).save_edits(meeting_id, run_id, {1: secret})
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    try:
        job_id = service.start_generation(meeting_id, "general")
        assert wait_terminal(service)["state"] == "completed"
        path = _metrics_path(store, meeting_id, job_id)
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert MetricsOllama.calls == data["post_attempts"] == 2
        assert data["post_count_complete"] is True
        assert data["model_calls"] == 1 and data["http_json_retries"] == 1
        assert data["state"] == "completed" and data["resumed"] is False
        assert data["wire_mode"] == "full"
        assert data["model"] == DEFAULT_MODEL and data["model_digest"] == "a" * 64
        first, second = data["posts"]
        assert first["done_reason"] == "length" and first["prompt_eval_count"] is None
        assert first["eval_count"] is None and first["total_duration_ns"] is None
        assert second["done_reason"] == "stop" and second["prompt_eval_count"] == 321
        assert second["prompt_eval_cached_count"] == 21
        assert second["eval_count"] == 123 and second["total_duration_ns"] == 2000
        assert second["prompt_eval_duration_ns"] == 400 and second["eval_duration_ns"] == 1500
        assert first["state"] == second["state"] == "finished"
        assert secret not in raw and "Nhóm đã thống nhất" not in raw
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cancelled_request_is_incomplete_and_resume_has_separate_metrics(tmp_path):
    BlockingOllama.entered.clear()
    BlockingOllama.release.clear()
    BlockingOllama.blocked = True
    BlockingOllama.dribble = False
    BlockingOllama.block_headers = False
    server, thread = _server(BlockingOllama)
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    try:
        first_job = service.start_generation(meeting_id, "general")
        assert BlockingOllama.entered.wait(10)
        assert service.cancel_generation(meeting_id, first_job)
        assert wait_terminal(service)["state"] == "cancelled"
        first = json.loads(_metrics_path(store, meeting_id, first_job).read_text(encoding="utf-8"))
        assert first["state"] == "cancelled" and first["post_count_complete"] is False
        assert first["post_attempts"] == 1 and first["posts"][0]["state"] == "interrupted"
        assert first["posts"][0]["eval_count"] is None
        BlockingOllama.blocked = False
        BlockingOllama.release.set()
        second_job = service.resume_generation(meeting_id)
        assert wait_terminal(service)["state"] == "completed"
        second = json.loads(
            _metrics_path(store, meeting_id, second_job).read_text(encoding="utf-8")
        )
        assert second["resumed"] is True and second["state"] == "completed"
        assert second["post_count_complete"] is True and second["post_attempts"] == 1
        assert second["posts"][0]["eval_count"] is None
    finally:
        BlockingOllama.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_split_validation_retry_and_reduce_are_counted_without_fake_post_numbers(tmp_path):
    import re
    import uuid

    from fahmm.models import InstalledModel
    from fahmm.storage import MeetingStore
    from fahmm.transcripts import TranscriptStore

    class SplitClient(ChunkClient):
        def __init__(self):
            super().__init__()
            self.retried = False

        def generate(self, _model, prompt, *, form=False):
            ids = [int(value) for value in re.findall(r"\[(\d+)\]", prompt)]
            if form and len(ids) > 2:
                raise OllamaOutputLimitError("Output limit")
            if form and not self.retried:
                self.retried = True
                return {"summary": "ngắn", "source_ids": ids[:1], "items": []}
            summary = (
                "Cuộc họp thống nhất triển khai toàn bộ kế hoạch thử nghiệm."
                if not form
                else "Nhóm thống nhất thử nghiệm các hạng mục đã trao đổi."
            )
            return {"summary": summary, "source_ids": ids[:1], **({"items": []} if form else {})}

    store = MeetingStore(tmp_path / "meetings")
    meeting_id, run_id = store.create({}), uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {"id": i, "start": float(i), "end": float(i + 1), "text": f"Nội dung nguồn số {i}."}
        for i in range(1, 5)
    ]
    TranscriptStore(store).save_run(meeting_id, run_id, model, "vi", {"duration": 10}, segments)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", SplitClient())
    job_id = service.start_generation(meeting_id, "general")
    assert wait_terminal(service)["state"] == "completed"
    data = json.loads(_metrics_path(store, meeting_id, job_id).read_text(encoding="utf-8"))
    assert data["split_attempts"]["chunk"] == 1
    assert data["validation_retries"] == 1 and data["reduce_calls"] == 1
    assert data["model_calls"] == 5
    assert data["post_attempts"] == 0 and data["post_count_complete"] is False


def test_metrics_write_failure_does_not_fail_generation(tmp_path, monkeypatch):
    from fahmm import local_metrics

    def full_disk(*_args, **_kwargs):
        raise OSError("private path should not be logged")

    monkeypatch.setattr(local_metrics, "_atomic_json", full_disk)
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    job_id = service.start_generation(meeting_id, "general")
    assert wait_terminal(service)["state"] == "completed"
    assert not _metrics_path(store, meeting_id, job_id).exists()


def test_untrusted_or_invalid_metric_fields_are_not_persisted(tmp_path):
    from fahmm.local_metrics import LocalGenerationMetrics

    metrics = LocalGenerationMetrics(tmp_path, "a" * 32, resumed=False)
    metrics.worker_event(1, "chunk", {"type": "post_started", "attempt": 1})
    metrics.worker_event(
        1,
        "chunk",
        {
            "type": "post_finished",
            "attempt": 1,
            "completed": True,
            "done_reason": "PRIVATE_WORD_FROM_RESPONSE",
            "prompt_eval_count": -1,
            "eval_count": True,
            "total_duration_ns": "PRIVATE_VALUE",
            "wall_seconds": float("nan"),
        },
    )
    metrics.finish("failed")
    raw = metrics.path.read_text(encoding="utf-8")
    row = json.loads(raw)["posts"][0]
    assert row["done_reason"] is None and row["prompt_eval_count"] is None
    assert row["eval_count"] is None and row["total_duration_ns"] is None
    assert row["wall_seconds"] is None and "PRIVATE" not in raw
