"""Opt-in short wire format must preserve fields and never guess citations."""

import copy
import io
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest
from test_local_minutes_checkpoint import ChunkClient, long_meeting, wait_terminal
from test_minutes_store import make_meeting_with_run

from fahmm.compact_minutes_wire import (
    COMPACT_FORM_SCHEMA,
    COMPACT_INSTRUCTIONS,
    SECTION_CODES,
    decode_compact_form,
    encode_compact_form,
)
from fahmm.local_llm import (
    _FORM_SCHEMA,
    DEFAULT_MODEL,
    WIRE_FORMAT_ENV,
    LocalMinutesJobs,
    OllamaClient,
    OllamaError,
    _wire_format,
)
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore


def full_form():
    return {
        "summary": "Nhóm đã thống nhất phạm vi triển khai trong cuộc họp.",
        "source_ids": [1, 2, 3, 4, 5, 6, 1],
        "items": [
            {
                "section": section,
                "label": f"  Nhãn {index}  ",
                "text": f"  Nội dung {index}  ",
                "method": "M" * 240,
                "data_source": "Nguồn gốc cụ thể",
                "open_point": "Cần xác nhận",
                "owner": "Nhóm A",
                "due_date": "Ngày 12",
                "source_ids": [1, 2, 3, 4, 5, 6, 1],
            }
            for index, section in enumerate(SECTION_CODES, 1)
        ],
    }


def make_six_segments(tmp_path):
    store = MeetingStore(tmp_path / "meetings")
    meeting_id, run_id = store.create({}), uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {"id": i, "start": float(i), "end": float(i + 0.5), "text": f"Nguồn số {i}."}
        for i in range(1, 7)
    ]
    TranscriptStore(store).save_run(meeting_id, run_id, model, "vi", {"duration": 10}, segments)
    return store, meeting_id


def test_compact_round_trip_preserves_every_section_field_and_citation():
    full = full_form()
    compact = encode_compact_form(full)
    assert decode_compact_form(compact) == full
    assert encode_compact_form(decode_compact_form(compact)) == compact
    assert [item["c"] for item in compact["i"]] == list(SECTION_CODES.values())
    assert len(json.dumps(compact, ensure_ascii=False)) < len(json.dumps(full, ensure_ascii=False))
    compact["i"][0]["r"].append(8)
    assert full["items"][0]["source_ids"] == [1, 2, 3, 4, 5, 6, 1]


def test_round_trip_keeps_optional_fields_absent():
    value = {
        "summary": "Nhóm đã thống nhất phạm vi triển khai trong cuộc họp.",
        "source_ids": [1],
        "items": [
            {
                "section": "project_actions",
                "label": "Kiểm tra",
                "text": "Cần kiểm tra.",
                "source_ids": [1],
            }
        ],
    }
    assert decode_compact_form(encode_compact_form(value)) == value


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.pop("s"),
        lambda x: x.update({"extra": 3}),
        lambda x: x.update({"r": [True]}),
        lambda x: x.update({"r": []}),
        lambda x: x.update({"r": list(range(9))}),
        lambda x: x["i"][0].update({"c": "bad"}),
        lambda x: x["i"][0].update({"r": [1, "2"]}),
        lambda x: x["i"][0].update({"o": None}),
        lambda x: x["i"][0].update({"unexpected": "value"}),
        lambda x: x["i"][0].pop("t"),
        lambda x: x["i"].append(copy.deepcopy(x["i"][0])),
    ],
)
def test_invalid_compact_forms_are_rejected(mutation):
    compact = encode_compact_form(full_form())
    mutation(compact)
    with pytest.raises(ValueError):
        decode_compact_form(compact)


def test_compact_opt_in_uses_explicit_schema_and_default_stays_full(monkeypatch):
    seen = []
    form = full_form()
    result = {"payload": encode_compact_form(form)}

    def fake_request(_self, _path, body, *, timeout):
        seen.append(body)
        event = {"message": {"content": json.dumps(result["payload"])}, "done": True}
        return io.BytesIO(json.dumps(event).encode())

    monkeypatch.setattr(OllamaClient, "_request", fake_request)
    assert OllamaClient().generate(DEFAULT_MODEL, "prompt", form=True, wire_mode="compact") == form
    assert seen[0]["format"] == COMPACT_FORM_SCHEMA
    assert seen[0]["messages"][1]["content"].endswith(COMPACT_INSTRUCTIONS)
    assert seen[0]["options"]["num_predict"] == 2200 and seen[0]["think"] is False
    result["payload"] = form
    assert OllamaClient().generate(DEFAULT_MODEL, "prompt", form=True) == form
    assert seen[1]["format"] == _FORM_SCHEMA
    assert seen[1]["messages"][1]["content"] == "prompt"
    monkeypatch.delenv(WIRE_FORMAT_ENV, raising=False)
    assert _wire_format() == "full"
    monkeypatch.setenv(WIRE_FORMAT_ENV, "invalid")
    with pytest.raises(OllamaError, match="wire format"):
        _wire_format()


def test_duplicate_json_keys_in_compact_response_are_rejected(monkeypatch):
    duplicate = '{"s":"Summary","r":[1],"i":[],"s":"other"}'
    event = {"message": {"content": duplicate}, "done": True}
    monkeypatch.setattr(
        OllamaClient, "_request", lambda *_args, **_kwargs: io.BytesIO(json.dumps(event).encode())
    )
    with pytest.raises(OllamaError, match="Duplicate fields"):
        OllamaClient().generate(DEFAULT_MODEL, "prompt", form=True, wire_mode="compact")


def test_invalid_compact_provider_response_is_not_guessed_or_silently_retried(monkeypatch):
    calls = []
    invalid = encode_compact_form(full_form())
    invalid["i"][0]["c"] = "unknown"

    def fake_request(_self, _path, _body, *, timeout):
        calls.append(1)
        event = {"message": {"content": json.dumps(invalid)}, "done": True}
        return io.BytesIO(json.dumps(event).encode())

    monkeypatch.setattr(OllamaClient, "_request", fake_request)
    with pytest.raises(OllamaError, match="Invalid compact AI form response"):
        OllamaClient().generate(DEFAULT_MODEL, "prompt", form=True, wire_mode="compact")
    assert calls == [1]


class CompactClient(ChunkClient):
    def generate(self, model, prompt, *, form=False):
        full = super().generate(model, prompt, form=form)
        return encode_compact_form(full) if form else full


def test_full_legacy_checkpoint_and_compact_mode_do_not_resume_each_other(tmp_path):
    store, meeting_id, _ = long_meeting(tmp_path)
    first = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient(fail_at=2))
    with pytest.raises(OllamaError, match="interruption"):
        first._generate(meeting_id, "general", wire_mode="full")
    path = first._checkpoint_path(meeting_id)
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy.pop("wire_mode")
    first._write_checkpoint(path, legacy)
    saved = path.read_bytes()
    with pytest.raises(OllamaError, match="does not match"):
        LocalMinutesJobs(store, tmp_path / "llm.json", CompactClient())._generate(
            meeting_id, "general", resume=True, wire_mode="compact"
        )
    assert path.read_bytes() == saved
    version = LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())._generate(
        meeting_id, "general", resume=True, wire_mode="full"
    )
    assert (
        MinutesStore(store).read_version(meeting_id, version)["manifest"]["origin"] == "local_llm"
    )


def test_compact_checkpoint_rejects_full_mode_and_can_resume_compact(tmp_path):
    store, meeting_id, _ = long_meeting(tmp_path)
    first = LocalMinutesJobs(store, tmp_path / "llm.json", CompactClient(fail_at=2))
    with pytest.raises(OllamaError, match="interruption"):
        first._generate(meeting_id, "general", wire_mode="compact")
    path = first._checkpoint_path(meeting_id)
    assert json.loads(path.read_text(encoding="utf-8"))["wire_mode"] == "compact"
    saved = path.read_bytes()
    with pytest.raises(OllamaError, match="does not match"):
        LocalMinutesJobs(store, tmp_path / "llm.json", ChunkClient())._generate(
            meeting_id, "general", resume=True, wire_mode="full"
        )
    assert path.read_bytes() == saved
    assert LocalMinutesJobs(store, tmp_path / "llm.json", CompactClient())._generate(
        meeting_id, "general", resume=True, wire_mode="compact"
    )


@pytest.mark.parametrize("change", ["schema", "mapping", "instructions"])
def test_compact_checkpoint_rejects_changed_wire_contract(tmp_path, monkeypatch, change):
    from fahmm import local_llm

    store, meeting_id, _ = long_meeting(tmp_path)
    first = LocalMinutesJobs(store, tmp_path / "llm.json", CompactClient(fail_at=2))
    with pytest.raises(OllamaError, match="interruption"):
        first._generate(meeting_id, "general", wire_mode="compact")
    path = first._checkpoint_path(meeting_id)
    saved = path.read_bytes()
    if change == "schema":
        changed = copy.deepcopy(local_llm.COMPACT_FORM_SCHEMA)
        changed["properties"]["s"]["maxLength"] = 449
        monkeypatch.setattr(local_llm, "COMPACT_FORM_SCHEMA", changed)
    elif change == "mapping":
        monkeypatch.setattr(
            local_llm, "SECTION_CODES", {**local_llm.SECTION_CODES, "project_actions": "xx"}
        )
    else:
        monkeypatch.setattr(local_llm, "COMPACT_INSTRUCTIONS", "different")
    with pytest.raises(OllamaError, match="does not match"):
        LocalMinutesJobs(store, tmp_path / "llm.json", CompactClient())._generate(
            meeting_id, "general", resume=True, wire_mode="compact"
        )
    assert path.read_bytes() == saved


def test_compact_output_preserves_all_sources_and_fields_in_saved_claims(tmp_path):
    store, meeting_id = make_six_segments(tmp_path)
    value = full_form()

    class Fixed(ChunkClient):
        def generate(self, _model, _prompt, *, form=False):
            assert form
            return encode_compact_form(value)

    version = LocalMinutesJobs(store, tmp_path / "llm.json", Fixed())._generate(
        meeting_id, "general", wire_mode="compact"
    )
    saved = MinutesStore(store).read_version(meeting_id, version)
    sections = saved["content"]["domain"]["sections"]
    assert [source["segment_id"] for source in sections["summary"][0]["sources"]] == value[
        "source_ids"
    ]
    for expected in value["items"]:
        actual = sections[expected["section"]][0]
        assert actual["text"] == expected["text"]
        for key in ("label", "method", "data_source", "open_point", "owner", "due_date"):
            assert actual[key] == expected[key]
        assert [source["segment_id"] for source in actual["sources"]] == expected["source_ids"]


@pytest.mark.parametrize("invalid_field", ["summary", "item"])
def test_compact_invalid_citation_does_not_silently_publish(tmp_path, invalid_field):
    store, meeting_id, _ = make_meeting_with_run(tmp_path)

    class InvalidCitation(ChunkClient):
        def generate(self, _model, _prompt, *, form=False):
            value = {
                "summary": "Nhóm thống nhất triển khai phạm vi thử nghiệm.",
                "source_ids": [1, 999] if invalid_field == "summary" else [1],
                "items": [
                    {
                        "section": "project_actions",
                        "label": "Kiểm tra",
                        "text": "Cần kiểm tra.",
                        "source_ids": [1, 999] if invalid_field == "item" else [1],
                    }
                ],
            }
            return encode_compact_form(value)

    service = LocalMinutesJobs(store, tmp_path / "llm.json", InvalidCitation())
    with pytest.raises(OllamaError, match="invalid (summary |source )?citation"):
        service._generate(meeting_id, "general", wire_mode="compact")
    assert not MinutesStore(store).list_versions(meeting_id)
    assert service.checkpoint_info(meeting_id)["available"]


class CompactHTTP(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict]] = []

    def do_GET(self):
        body = json.dumps(
            {"models": [{"name": DEFAULT_MODEL, "size": 1, "digest": "a" * 64}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(request)
        body = (
            json.dumps(
                {
                    "message": {"content": json.dumps(encode_compact_form(full_form()))},
                    "done": True,
                    "done_reason": "stop",
                }
            )
            + "\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def test_compact_mode_flows_through_spawned_http_worker_and_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv(WIRE_FORMAT_ENV, "compact")
    CompactHTTP.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), CompactHTTP)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store, meeting_id = make_six_segments(tmp_path)
    service = LocalMinutesJobs(
        store, tmp_path / "llm.json", OllamaClient(f"http://127.0.0.1:{server.server_port}")
    )
    try:
        job_id = service.start_generation(meeting_id, "general")
        status = wait_terminal(service)
        assert status["state"] == "completed", status
        assert len(CompactHTTP.requests) == 1
        assert CompactHTTP.requests[0]["format"] == COMPACT_FORM_SCHEMA
        assert COMPACT_INSTRUCTIONS in CompactHTTP.requests[0]["messages"][1]["content"]
        metrics = store._meeting_dir(meeting_id) / "minutes" / "ai-metrics" / f"{job_id}.json"
        assert json.loads(metrics.read_text(encoding="utf-8"))["wire_mode"] == "compact"
        saved = MinutesStore(store).read_version(meeting_id, status["versionId"])
        assert [
            s["segment_id"]
            for s in saved["content"]["domain"]["sections"]["sqdcm_kpis"][0]["sources"]
        ] == full_form()["items"][2]["source_ids"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
