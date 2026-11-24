"""Durable local minutes and cancellation at real HTTP boundaries."""

import io
import json
import multiprocessing
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil
import pytest
from test_minutes_store import make_meeting_with_run

from fahmm.local_llm import DEFAULT_MODEL, LocalMinutesJobs, OllamaClient, OllamaError, _chunks
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


class ChunkClient:
    def __init__(self, fail_at=None, revision="revision-a"):
        self.prompts = []
        self.fail_at = fail_at
        self.revision = revision

    def models(self):
        return [DEFAULT_MODEL]

    def model_revision(self, _model):
        return self.revision

    def generate(self, _model, prompt, *, form=False):
        self.prompts.append(prompt)
        if len(self.prompts) == self.fail_at:
            raise OllamaError("Simulated interruption")
        identifier = int(re.search(r"\[(\d+)\]", prompt).group(1))
        return {
            "summary": (
                "Cuộc họp tổng hợp các bước triển khai và thống nhất phạm vi thử nghiệm."
                if "các tóm tắt từng phần" in prompt
                else "Nhóm đã thống nhất phạm vi triển khai trong cuộc họp."
            ),
            "source_ids": [identifier],
            **({"items": []} if form else {}),
        }


def long_meeting(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting_id = store.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {
            "id": i,
            "start": i * 20.0,
            "end": i * 20.0 + 10,
            "text": f"Nội dung nguồn {i}. " + "Thông tin thử nghiệm. " * 175,
        }
        for i in range(1, 4)
    ]
    TranscriptStore(store).save_run(meeting_id, run_id, model, "vi", {"duration": 70}, segments)
    return store, meeting_id, run_id


def test_interrupted_chunk_resumes_without_repeating_completed_chunk(tmp_path):
    store, meeting_id, _ = long_meeting(tmp_path)
    first = ChunkClient(fail_at=2)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", first)
    with pytest.raises(OllamaError, match="interruption"):
        service._generate(meeting_id, "general")
    saved = json.loads(service._checkpoint_path(meeting_id).read_text(encoding="utf-8"))
    assert len(saved["notes"]) == 1 and len(saved["pending"]) == 2
    again = ChunkClient()
    restarted = LocalMinutesJobs(store, tmp_path / "llm.json", again)
    version = restarted._generate(meeting_id, "general", resume=True)
    assert "[1] Nội dung nguồn 1." not in again.prompts[0]
    assert restarted.checkpoint_info(meeting_id)["available"] is False
    result = MinutesStore(store).read_version(meeting_id, version)
    assert result["content"]["domain"]["sections"]["summary"][0]["sources"]
    assert len(MinutesStore(store).list_versions(meeting_id)) == 1


def _crash_during_second_chunk(root, meeting_id, config):
    class CrashClient(ChunkClient):
        def generate(self, model, prompt, *, form=False):
            if self.prompts:
                os._exit(91)
            return super().generate(model, prompt, form=form)

    LocalMinutesJobs(MeetingStore(root), config, CrashClient())._generate(meeting_id, "general")


def test_process_kill_releases_lease_and_restores_committed_chunk(tmp_path):
    store, meeting_id, _ = long_meeting(tmp_path)
    process = multiprocessing.get_context("spawn").Process(
        target=_crash_during_second_chunk,
        args=(store.root, meeting_id, tmp_path / "llm.json"),
    )
    process.start()
    process.join(timeout=15)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        pytest.fail("Test process did not reach the crash point")
    assert process.exitcode == 91
    client = ChunkClient()
    restarted = LocalMinutesJobs(store, tmp_path / "llm.json", client)
    assert restarted.checkpoint_info(meeting_id)["progress"] > 0
    restarted._generate(meeting_id, "general", resume=True)
    assert "[1] Nội dung nguồn 1." not in client.prompts[0]


def test_resume_preserves_completed_reduction_groups(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting_id = store.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {
            "id": i,
            "start": i * 20.0,
            "end": i * 20.0 + 10,
            "text": f"Nội dung nguồn {i}. " + "Thông tin thử nghiệm. " * 175,
        }
        for i in range(1, 9)
    ]
    TranscriptStore(store).save_run(meeting_id, run_id, model, "vi", {"duration": 180}, segments)

    class ReduceClient(ChunkClient):
        def __init__(self, fail=False):
            super().__init__()
            self.reduce_calls = 0
            self.fail = fail

        def generate(self, _model, prompt, *, form=False):
            self.prompts.append(prompt)
            identifier = int(re.search(r"\[(\d+)\]", prompt).group(1))
            if "các tóm tắt từng phần" in prompt:
                self.reduce_calls += 1
                if self.fail and self.reduce_calls == 2:
                    raise OllamaError("Interrupted reduction")
                summary = (
                    f"Cuộc họp thống nhất triển khai các bước thử nghiệm số {self.reduce_calls}."
                )
            else:
                summary = (
                    f"Nhóm đã thống nhất thử nghiệm phần {identifier}. " + "nội dung dữ liệu " * 19
                )
            return {
                "summary": summary,
                "source_ids": [identifier],
                **({"items": []} if form else {}),
            }

    service = LocalMinutesJobs(store, tmp_path / "llm.json", ReduceClient(fail=True))
    with pytest.raises(OllamaError, match="Interrupted reduction"):
        service._generate(meeting_id, "general")
    state = json.loads(service._checkpoint_path(meeting_id).read_text(encoding="utf-8"))
    assert state["phase"] == "reduce" and len(state["merged"]) == 1 and state["groups"]
    client = ReduceClient()
    restarted = LocalMinutesJobs(store, tmp_path / "llm.json", client)
    restarted._generate(meeting_id, "general", resume=True)
    assert "các tóm tắt từng phần" in client.prompts[0]
    assert "[0]" not in client.prompts[0]
    assert len(MinutesStore(store).list_versions(meeting_id)) == 1


@pytest.mark.parametrize("changed", ["transcript", "model", "template"])
def test_resume_rejects_changed_inputs_without_overwriting_checkpoint(tmp_path, changed):
    store, meeting_id, run_id = long_meeting(tmp_path)
    original = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient(fail_at=2))
    with pytest.raises(OllamaError):
        original._generate(meeting_id, "general")
    path = original._checkpoint_path(meeting_id)
    checkpoint = path.read_bytes()
    client = ChunkClient(revision="revision-b" if changed == "model" else "revision-a")
    if changed == "transcript":
        TranscriptStore(store).save_edits(meeting_id, run_id, {1: "Nội dung đã thay đổi"})
    elif changed == "template":
        template = MinutesStore(store).read_template(meeting_id)
        template["topic_limit"] = 7
        MinutesStore(store).save_template(meeting_id, template)
    with pytest.raises(OllamaError, match="does not match"):
        LocalMinutesJobs(store, tmp_path / "llm.json", client)._generate(
            meeting_id, "general", resume=True
        )
    assert path.read_bytes() == checkpoint
    assert not client.prompts


def test_corrupt_checkpoint_requires_explicit_discard(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    path = service._checkpoint_path(meeting_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")
    assert service.checkpoint_info(meeting_id)["error"]
    with pytest.raises(ValueError, match="unreadable"):
        service.resume_generation(meeting_id)
    assert path.exists()
    service.discard_checkpoint(meeting_id)
    assert not path.exists()


def test_corrupt_but_valid_json_checkpoint_is_detected(tmp_path):
    store, meeting_id, _ = long_meeting(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient(fail_at=2))
    with pytest.raises(OllamaError):
        service._generate(meeting_id, "general")
    path = service._checkpoint_path(meeting_id)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["notes"][0]["text"] = "Nội dung đã bị sửa trong checkpoint"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert service.checkpoint_info(meeting_id)["error"]


def test_model_call_budget_stops_without_losing_completed_chunks(tmp_path, monkeypatch):
    from fahmm import local_llm

    monkeypatch.setattr(local_llm, "MAX_MODEL_CALLS", 1)
    store, meeting_id, _ = long_meeting(tmp_path)
    client = ChunkClient()
    service = LocalMinutesJobs(store, tmp_path / "llm.json", client)
    with pytest.raises(local_llm.GenerationDeadline, match="model-call limit"):
        service._generate(meeting_id, "general")
    state = json.loads(service._checkpoint_path(meeting_id).read_text(encoding="utf-8"))
    assert len(client.prompts) == 1 and len(state["notes"]) == 1


def test_single_large_segment_is_bounded_before_prompt_and_retains_source():
    original = "Nội dung họp. " * 3000
    chunks = _chunks([{"id": 7, "text": original}], 6500)
    rows = [row for chunk in chunks for row in chunk]
    assert len(rows) > 1
    assert all(sum(len(row["text"]) + 30 for row in chunk) <= 6500 for chunk in chunks)
    assert all(row["id"] == 7 for row in rows)
    assert " ".join(" ".join(row["text"] for row in rows).split()) == " ".join(original.split())


def test_unbounded_stream_line_is_rejected(monkeypatch):
    from fahmm import local_llm

    monkeypatch.setattr(local_llm, "MAX_STREAM_LINE_BYTES", 100)
    monkeypatch.setattr(OllamaClient, "_request", lambda *_args, **_kwargs: io.BytesIO(b"x" * 101))
    with pytest.raises(OllamaError, match="streaming size limit"):
        OllamaClient().generate(DEFAULT_MODEL, "Dữ liệu thử")


def test_stream_total_size_is_rejected(monkeypatch):
    from fahmm import local_llm

    event = b'{"message":{"content":"a"},"done":false}\n'
    monkeypatch.setattr(local_llm, "MAX_STREAM_BYTES", 100)
    monkeypatch.setattr(OllamaClient, "_request", lambda *_args, **_kwargs: io.BytesIO(event * 10))
    with pytest.raises(OllamaError, match="streaming size limit"):
        OllamaClient().generate(DEFAULT_MODEL, "Dữ liệu thử")


def test_template_changed_during_final_revision_is_rejected(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    minutes = MinutesStore(store)

    class RaceClient(ChunkClient):
        def __init__(self):
            super().__init__()
            self.revision_calls = 0

        def model_revision(self, _model):
            self.revision_calls += 1
            if self.revision_calls == 2:
                template = minutes.read_template(meeting_id)
                template["topic_limit"] = 7
                minutes.save_template(meeting_id, template)
            return self.revision

    service = LocalMinutesJobs(store, tmp_path / "llm.json", RaceClient())
    with pytest.raises(OllamaError, match="changed"):
        service._generate(meeting_id, "general")
    assert not minutes.list_versions(meeting_id)
    assert service.checkpoint_info(meeting_id)["available"]


def test_active_transcript_changed_during_final_revision_is_rejected(tmp_path):
    store, meeting_id, original_run = make_meeting_with_run(tmp_path)
    other_run = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    transcripts = TranscriptStore(store)
    segments = transcripts.read_run(meeting_id, original_run)["working"]
    transcripts.save_run(meeting_id, other_run, model, "vi", {"duration": 2}, segments)
    transcripts.select_run(meeting_id, original_run)

    class RaceClient(ChunkClient):
        def __init__(self):
            super().__init__()
            self.revision_calls = 0

        def model_revision(self, _model):
            self.revision_calls += 1
            if self.revision_calls == 2:
                transcripts.select_run(meeting_id, other_run)
            return self.revision

    service = LocalMinutesJobs(store, tmp_path / "llm.json", RaceClient())
    with pytest.raises(OllamaError, match="changed"):
        service._generate(meeting_id, "general")
    assert not MinutesStore(store).list_versions(meeting_id)
    assert store.metadata(meeting_id)["active_run"] == other_run


def _edit_from_another_process(root, meeting_id, run_id, started):
    started.set()
    TranscriptStore(MeetingStore(root)).save_edits(meeting_id, run_id, {1: "Văn bản đã sửa"})


def test_cross_process_transcript_edit_waits_for_final_commit(tmp_path):
    store, meeting_id, run_id = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    entered = threading.Event()
    release = threading.Event()
    save = service.minutes.save_version

    def slow_save(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return save(*args, **kwargs)

    service.minutes.save_version = slow_save
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    process = context.Process(
        target=_edit_from_another_process, args=(store.root, meeting_id, run_id, started)
    )
    try:
        service.start_generation(meeting_id, "general")
        assert entered.wait(5)
        process.start()
        assert started.wait(5)
        time.sleep(0.3)
        assert process.is_alive()
        release.set()
        assert wait_terminal(service)["state"] == "completed"
        process.join(timeout=10)
        assert process.exitcode == 0
        assert (
            TranscriptStore(store).read_run(meeting_id, run_id)["working"][0]["text"]
            == "Văn bản đã sửa"
        )
        assert MinutesStore(store).list_versions(meeting_id)
    finally:
        release.set()
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)


def test_cancel_while_waiting_for_meeting_lock_is_prompt_and_reported(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    with store.input_guard(meeting_id):
        job_id = service.start_generation(meeting_id, "general")
        time.sleep(0.1)
        started = time.monotonic()
        assert service.cancel_generation(meeting_id, job_id)
        assert wait_terminal(service, timeout=3)["state"] == "cancelled"
        assert time.monotonic() - started < 2
    assert not MinutesStore(store).list_versions(meeting_id)


def test_total_deadline_includes_wait_for_meeting_lock(tmp_path, monkeypatch):
    from fahmm import local_llm

    monkeypatch.setattr(local_llm, "JOB_SECONDS", 0.4)
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    with store.input_guard(meeting_id):
        service.start_generation(meeting_id, "general")
        started = time.monotonic()
        assert wait_terminal(service, timeout=3)["state"] == "timed_out"
        assert time.monotonic() - started < 2
    assert not MinutesStore(store).list_versions(meeting_id)


def test_cancel_during_final_lock_wait_never_saves_version(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    revision_started = threading.Event()
    proceed = threading.Event()

    class BlockingRevision(ChunkClient):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def model_revision(self, _model):
            self.calls += 1
            if self.calls == 2:
                revision_started.set()
                assert proceed.wait(5)
            return self.revision

    service = LocalMinutesJobs(store, tmp_path / "llm.json", BlockingRevision())
    job_id = service.start_generation(meeting_id, "general")
    assert revision_started.wait(5)
    with store.input_guard(meeting_id):
        proceed.set()
        time.sleep(0.1)
        assert service.cancel_generation(meeting_id, job_id)
        assert wait_terminal(service, timeout=3)["state"] == "cancelled"
    assert not MinutesStore(store).list_versions(meeting_id)
    assert service.checkpoint_info(meeting_id)["available"]


def test_crash_after_save_reuses_version_instead_of_duplicating(tmp_path):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    save = service.minutes.save_version

    def save_then_crash(*args, **kwargs):
        save(*args, **kwargs)
        raise OSError("Simulated crash after version commit")

    service.minutes.save_version = save_then_crash
    with pytest.raises(OSError, match="after version commit"):
        service._generate(meeting_id, "general")
    versions = MinutesStore(store).list_versions(meeting_id)
    assert len(versions) == 1
    restarted = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
    version = restarted._generate(meeting_id, "general", resume=True)
    assert version == versions[0]["version_id"]
    assert len(MinutesStore(store).list_versions(meeting_id)) == 1


class BlockingOllama(BaseHTTPRequestHandler):
    entered = threading.Event()
    release = threading.Event()
    blocked = True
    dribble = False
    block_headers = False

    def do_GET(self):
        data = json.dumps(
            {"models": [{"name": DEFAULT_MODEL, "size": 1, "digest": "sha256:test"}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.entered.set()
        if self.blocked and self.block_headers:
            self.release.wait(15)
        try:
            self.send_response(200)
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return
        if self.blocked and not self.block_headers:
            self.release.wait(15)
        if self.dribble:
            try:
                while not self.release.wait(0.1):
                    self.wfile.write(b'{"message":{"content":""},"done":false}\n')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
        data = {
            "summary": "Nhóm đã thống nhất phạm vi triển khai trong cuộc họp.",
            "source_ids": [1],
            "items": [],
        }
        try:
            self.wfile.write(
                (
                    json.dumps({"message": {"content": json.dumps(data)}, "done": True}) + "\n"
                ).encode()
            )
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_args):
        pass


def wait_terminal(service, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.status("_generation")
        if status["state"] not in ("running", "cancelling", "saving"):
            return status
        time.sleep(0.05)
    pytest.fail("Local minutes did not stop within the deadline")


@pytest.mark.parametrize("block_headers", [False, True])
def test_cancel_interrupts_blocked_http_and_progress_can_resume(tmp_path, block_headers):
    BlockingOllama.entered.clear()
    BlockingOllama.release.clear()
    BlockingOllama.blocked = True
    BlockingOllama.dribble = False
    BlockingOllama.block_headers = block_headers
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingOllama)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    try:
        job_id = service.start_generation(meeting_id, "general")
        assert BlockingOllama.entered.wait(10)
        started = time.monotonic()
        assert service.cancel_generation(meeting_id, job_id) is True
        assert service.cancel_generation(meeting_id, job_id) is True
        assert wait_terminal(service)["state"] == "cancelled"
        assert time.monotonic() - started < 5
        assert not MinutesStore(store).list_versions(meeting_id)
        assert service.checkpoint_info(meeting_id)["available"]
        BlockingOllama.blocked = False
        BlockingOllama.release.set()
        next_job = service.resume_generation(meeting_id)
        assert next_job != job_id
        assert service.cancel_generation(meeting_id, job_id) is False
        assert wait_terminal(service)["state"] == "completed"
        assert len(MinutesStore(store).list_versions(meeting_id)) == 1
    finally:
        BlockingOllama.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_until_parent_is_killed(root, meeting_id, config, url):
    service = LocalMinutesJobs(MeetingStore(root), config, OllamaClient(url))
    service.start_generation(meeting_id, "general")
    while True:
        time.sleep(1)


def test_orphan_http_worker_exits_when_owning_process_is_killed(tmp_path):
    BlockingOllama.entered.clear()
    BlockingOllama.release.clear()
    BlockingOllama.blocked = True
    BlockingOllama.dribble = False
    BlockingOllama.block_headers = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingOllama)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_run_until_parent_is_killed,
        args=(
            store.root,
            meeting_id,
            tmp_path / "llm.json",
            f"http://127.0.0.1:{server.server_port}",
        ),
    )
    children = []
    try:
        process.start()
        assert BlockingOllama.entered.wait(10)
        children = psutil.Process(process.pid).children(recursive=True)
        assert children
        process.terminate()
        process.join(timeout=5)
        _gone, alive = psutil.wait_procs(children, timeout=5)
        assert not alive, "HTTP request worker outlived its owning process"
        service = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())
        assert service.checkpoint_info(meeting_id)["available"]
    finally:
        BlockingOllama.release.set()
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        for child in children:
            try:
                if child.is_running():
                    child.terminate()
            except psutil.NoSuchProcess:
                pass
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_request_wall_clock_limit_interrupts_a_silent_http_stream(tmp_path, monkeypatch):
    from fahmm import local_llm

    monkeypatch.setattr(local_llm, "REQUEST_SECONDS", 4.0)
    BlockingOllama.entered.clear()
    BlockingOllama.release.clear()
    BlockingOllama.blocked = True
    BlockingOllama.dribble = False
    BlockingOllama.block_headers = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingOllama)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    original_request = service._model_request

    def request(operation, model, prompt="", *, form=False, phase="chunk"):
        if operation == "revision":
            return "a" * 64
        return original_request(operation, model, prompt, form=form, phase=phase)

    monkeypatch.setattr(service, "_model_request", request)
    try:
        service.start_generation(meeting_id, "general")
        assert BlockingOllama.entered.wait(10)
        status = wait_terminal(service)
        assert status["state"] == "timed_out"
        assert "time limit" in status["error"]
        assert not MinutesStore(store).list_versions(meeting_id)
    finally:
        BlockingOllama.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_stream_with_regular_tokens_still_has_a_wall_clock_limit(tmp_path, monkeypatch):
    from fahmm import local_llm

    monkeypatch.setattr(local_llm, "REQUEST_SECONDS", 4.0)
    BlockingOllama.entered.clear()
    BlockingOllama.release.clear()
    BlockingOllama.blocked = False
    BlockingOllama.dribble = True
    BlockingOllama.block_headers = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingOllama)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store, meeting_id, _ = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    original_request = service._model_request

    def request(operation, model, prompt="", *, form=False, phase="chunk"):
        if operation == "revision":
            return "a" * 64
        return original_request(operation, model, prompt, form=form, phase=phase)

    monkeypatch.setattr(service, "_model_request", request)
    try:
        service.start_generation(meeting_id, "general")
        assert BlockingOllama.entered.wait(10)
        assert wait_terminal(service)["state"] == "timed_out"
        assert service.checkpoint_info(meeting_id)["available"]
        assert not MinutesStore(store).list_versions(meeting_id)
    finally:
        BlockingOllama.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        BlockingOllama.dribble = False
