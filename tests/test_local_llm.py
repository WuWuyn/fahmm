"""Local semantic minutes stay source-linked and preserve prior versions on failure."""

import io
import json
import re
import time
import urllib.error
import uuid

import pytest
from test_bridge_cloud import call
from test_minutes_store import make_meeting_with_run

from fahmm.bridge.server import BridgeApplication
from fahmm.local_llm import (
    DEFAULT_MODEL,
    LocalMinutesJobs,
    OllamaClient,
    OllamaError,
    OllamaOutputLimitError,
    _chunks,
    _ensure_explicit_handoffs,
    _form_items,
    _split_chunk,
    _summary,
)
from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel


class FakeOllama:
    def __init__(self):
        self.installed = [DEFAULT_MODEL]
        self.prompts = []

    def models(self):
        return self.installed

    def generate(self, model, prompt, *, form=False):
        assert model == DEFAULT_MODEL
        self.prompts.append(prompt)
        result = {"summary": "Nhóm đã chốt phạm vi thử nghiệm cho bản đầu.", "source_ids": [1]}
        if form:
            result["items"] = [
                {
                    "section": "project_actions",
                    "label": "Thử nghiệm",
                    "text": "Nhóm triển khai thử nghiệm bản đầu.",
                    "method": "Chưa rõ",
                    "data_source": "Chưa rõ",
                    "open_point": "Chưa rõ",
                    "owner": "Chưa rõ",
                    "due_date": "Chưa rõ",
                    "source_ids": [1],
                }
            ]
        return result

    def pull(self, model, progress):
        self.installed.append(model)
        progress(1.0)


def test_semantic_minutes_use_existing_form_and_exact_transcript_sources(tmp_path):
    meetings, meeting_id, run_id = make_meeting_with_run(tmp_path)
    service = LocalMinutesJobs(meetings, tmp_path / "llm.json", FakeOllama())
    version_id = service._generate(meeting_id, "general")
    saved = MinutesStore(meetings).read_version(meeting_id, version_id)
    assert saved["manifest"]["origin"] == "local_llm"
    sections = saved["content"]["domain"]["sections"]
    assert {"summary", "topics", "decisions"} <= set(sections)
    claim = sections["summary"][0]
    assert claim["text"] == "Nhóm đã chốt phạm vi thử nghiệm cho bản đầu."
    assert claim["sources"] == [
        {
            "run_id": run_id,
            "segment_id": 1,
            "start": 0.0,
            "end": 2.0,
            "excerpt": "Đã thống nhất thử nghiệm.",
        }
    ]
    assert sections["decisions"][0]["origin"] == "extractive"
    assert saved["content"]["format"] == "denso_warehouse"
    assert sections["project_actions"][0]["sources"][0]["segment_id"] == 1
    markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, version_id)
    assert "## 6. Công việc phía nhóm dự án FPT triển khai" in markdown
    assert "| Công việc cụ thể | Thời hạn |" in markdown
    assert "(Nguồn:" not in markdown
    assert "Local Ollama DENSO-form draft" in markdown
    edited = MinutesStore(meetings).edit_version(meeting_id, version_id, saved["content"])
    assert (
        MinutesStore(meetings).read_version(meeting_id, edited)["manifest"]["source_origin"]
        == "local_llm"
    )


def test_invalid_model_citations_cannot_save_a_version(tmp_path):
    meetings, meeting_id, _ = make_meeting_with_run(tmp_path)

    class UnsupportedSource(FakeOllama):
        def generate(self, model, prompt, *, form=False):
            return {
                "summary": "Đây là bản tóm tắt có nguồn không hợp lệ.",
                "source_ids": [999],
                "items": [],
            }

    service = LocalMinutesJobs(meetings, tmp_path / "llm.json", UnsupportedSource())
    with pytest.raises(OllamaError, match="incomplete or too long"):
        service._generate(meeting_id, "general")
    assert MinutesStore(meetings).list_versions(meeting_id) == []


def test_chunking_and_summary_citations_are_bounded():
    segments = [{"id": index, "start": index, "text": "Nội dung " * 20} for index in range(100)]
    chunks = _chunks(segments, 500)
    assert len(chunks) > 1
    assert [item["id"] for chunk in chunks for item in chunk] == list(range(100))
    assert _summary(
        {"summary": "Nhóm thống nhất phạm vi thử nghiệm trên bản đầu.", "source_ids": [1, 99]},
        {1},
        "[1] Câu nguồn",
    ) == {"text": "Nhóm thống nhất phạm vi thử nghiệm trên bản đầu.", "source_ids": [1]}


def test_explicit_handoffs_fill_omitted_form_categories_without_inventing_deadlines():
    run_id = "r" * 32
    segments = [
        {
            "id": 1,
            "start": 0.0,
            "end": 2.0,
            "text": "Nhóm FPT sẽ cập nhật mô hình 3D theo kích thước thực tế.",
        },
        {"id": 2, "start": 2.0, "end": 4.0, "text": "DENSO cần cung cấp kích thước kệ và lối đi."},
    ]
    sections = {}
    _ensure_explicit_handoffs(sections, segments, run_id)
    assert sections["project_actions"][0]["origin"] == "extractive"
    assert sections["project_actions"][0]["due_date"] == "Chưa rõ"
    assert sections["partner_support"][0]["sources"][0]["segment_id"] == 2
    assert (
        _form_items(
            {
                "items": [
                    {"section": "project_actions", "text": "Không có nguồn", "source_ids": [999]}
                ]
            },
            {1, 2},
            {item["id"]: item for item in segments},
            run_id,
        )
        == {}
    )
    parsed = _form_items(
        {
            "items": [
                {
                    "section": "project_actions",
                    "label": "Kiểm tra",
                    "text": "Kiểm tra mô hình.",
                    "owner": None,
                    "source_ids": [1],
                }
            ]
        },
        {1, 2},
        {item["id"]: item for item in segments},
        run_id,
    )
    assert parsed["project_actions"][0]["owner"] == "Chưa rõ"
    generic = [{"id": 3, "start": 4.0, "end": 5.0, "text": "Nhóm dự án sẽ kiểm tra mô hình."}]
    extracted = {}
    _ensure_explicit_handoffs(extracted, generic, run_id)
    assert extracted["project_actions"][0]["owner"] == "Chưa rõ"


def test_connection_failure_does_not_split_or_repeat_requests(tmp_path):
    class Unavailable(FakeOllama):
        def generate(self, model, prompt, *, form=False):
            self.prompts.append(prompt)
            raise OllamaError("Ollama is unavailable")

    meetings, meeting_id, _ = make_meeting_with_run(tmp_path)
    client = Unavailable()
    with pytest.raises(OllamaError, match="unavailable"):
        LocalMinutesJobs(meetings, tmp_path / "llm.json", client)._generate(meeting_id, "general")
    assert len(client.prompts) == 1


def test_selection_is_persisted_and_only_installed_models_are_allowed(tmp_path):
    meetings, _, _ = make_meeting_with_run(tmp_path)
    config = tmp_path / "llm.json"
    service = LocalMinutesJobs(meetings, config, FakeOllama())
    assert service.availability()["ready"] is True
    with pytest.raises(ValueError, match="Install"):
        service.select("unavailable:latest")
    service.select(DEFAULT_MODEL)
    assert json.loads(config.read_text(encoding="utf-8"))["model"] == DEFAULT_MODEL


def test_only_downloaded_ollama_models_are_offered_for_private_minutes(monkeypatch):
    payload = {
        "models": [
            {"name": DEFAULT_MODEL, "size": 986000000},
            {"name": "remote:cloud", "size": 0},
            {"name": "unknown", "size": 0},
        ]
    }
    monkeypatch.setattr(
        OllamaClient, "_request", lambda *_args, **_kwargs: io.BytesIO(json.dumps(payload).encode())
    )
    assert OllamaClient().models() == [DEFAULT_MODEL]


def test_truncated_form_json_retries_with_more_output_without_losing_items(monkeypatch):
    requests = []
    responses = iter(
        [
            {
                "message": {"content": '{"summary":"unfinished'},
                "done_reason": "length",
                "done": True,
            },
            {
                "message": {
                    "content": json.dumps(
                        {"summary": "Bản nháp có dẫn nguồn.", "source_ids": [1], "items": []}
                    )
                },
                "done_reason": "stop",
                "done": True,
            },
        ]
    )

    def fake_request(_self, _path, body, *, timeout):
        requests.append(body)
        return io.BytesIO(json.dumps(next(responses)).encode())

    monkeypatch.setattr(OllamaClient, "_request", fake_request)
    assert OllamaClient().generate(DEFAULT_MODEL, "Nguồn hư cấu", form=True)["items"] == []
    assert [request["format"]["properties"]["items"]["maxItems"] for request in requests] == [8, 8]
    assert [request["options"]["num_predict"] for request in requests] == [2200, 3500]
    assert all(request["think"] is False for request in requests)


def test_invalid_summary_is_retried_before_failing(tmp_path):
    class RetryOllama(FakeOllama):
        def generate(self, model, prompt, *, form=False):
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return {"summary": "Quá ngắn", "source_ids": [1], "items": []}
            return {
                "summary": "Nhóm thống nhất thực hiện thử nghiệm theo phạm vi đã trao đổi.",
                "source_ids": [1],
                "items": [],
            }

    meetings, meeting_id, _ = make_meeting_with_run(tmp_path)
    client = RetryOllama()
    version = LocalMinutesJobs(meetings, tmp_path / "llm.json", client)._generate(
        meeting_id, "general"
    )
    assert version
    assert len(client.prompts) == 2
    assert "Kết quả trước chưa hợp lệ" in client.prompts[1]


def test_truncated_summary_json_retries_with_more_output_tokens(monkeypatch):
    requests = []
    responses = iter(
        [
            {"message": {"content": "{"}, "done_reason": "length", "done": True},
            {
                "message": {
                    "content": json.dumps({"summary": "Bản nháp có dẫn nguồn.", "source_ids": [1]})
                },
                "done_reason": "stop",
                "done": True,
            },
        ]
    )

    def fake_request(_self, _path, body, *, timeout):
        requests.append(body)
        return io.BytesIO(json.dumps(next(responses)).encode())

    monkeypatch.setattr(OllamaClient, "_request", fake_request)
    assert OllamaClient().generate(DEFAULT_MODEL, "Nguồn hư cấu")["source_ids"] == [1]
    assert [request["options"]["num_predict"] for request in requests] == [350, 700]
    assert all(request["think"] is False for request in requests)


def test_two_truncated_responses_signal_a_splittable_output_limit(monkeypatch):
    monkeypatch.setattr(
        OllamaClient,
        "_request",
        lambda *_args, **_kwargs: io.BytesIO(
            json.dumps(
                {"message": {"content": "{"}, "done_reason": "length", "done": True}
            ).encode()
        ),
    )
    with pytest.raises(OllamaOutputLimitError):
        OllamaClient().generate(DEFAULT_MODEL, "Nguồn hư cấu", form=True)


def test_streamed_chunks_are_joined_and_incomplete_stream_is_rejected(monkeypatch):
    body = json.dumps({"summary": "Nhóm thống nhất thử nghiệm bản đầu.", "source_ids": [1]})
    events = [
        {"message": {"content": body[:15]}, "done": False},
        {"message": {"content": body[15:]}, "done": False},
        {"message": {"content": ""}, "done": True, "done_reason": "stop"},
    ]
    requests = []

    def request(_self, _path, request_body, *, timeout):
        requests.append(request_body)
        return io.BytesIO("\n".join(json.dumps(event) for event in events).encode())

    monkeypatch.setattr(OllamaClient, "_request", request)
    assert OllamaClient().generate(DEFAULT_MODEL, "Dữ liệu thử")["source_ids"] == [1]
    assert requests[0]["stream"] is True
    events.pop()
    with pytest.raises(OllamaError, match="before finishing"):
        OllamaClient().generate(DEFAULT_MODEL, "Dữ liệu thử")


def test_http_errors_are_not_reported_as_connection_failures(monkeypatch):
    from fahmm import local_llm

    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError("http://127.0.0.1", 500, "failure", {}, None)

    monkeypatch.setattr(local_llm._OPENER, "open", fail)
    with pytest.raises(OllamaError, match="HTTP 500"):
        OllamaClient()._request("/api/chat", {})


def test_overloaded_form_part_is_split_and_all_sources_survive(tmp_path):
    from fahmm.storage import MeetingStore
    from fahmm.transcripts import TranscriptStore

    class TruncatingOllama(FakeOllama):
        def generate(self, model, prompt, *, form=False):
            self.prompts.append(prompt)
            evidence = prompt.split("<nguon>\n", 1)[1].split("\n</nguon>", 1)[0]
            ids = [int(value) for value in re.findall(r"\[(\d+)\]", evidence)]
            if form and len(ids) > 2:
                raise OllamaOutputLimitError("Ollama stopped at its output limit")
            summary = (
                "Toàn cuộc họp xác nhận các bước thử nghiệm của nhóm dự án."
                if "các tóm tắt từng phần" in prompt
                else "Nhóm đã thống nhất các bước thử nghiệm cho bản đầu."
            )
            result = {"summary": summary, "source_ids": ids[:1]}
            if form:
                result["items"] = [
                    {
                        "section": "project_actions",
                        "label": "Thử nghiệm",
                        "text": "Nhóm triển khai thử nghiệm bản đầu.",
                        "source_ids": ids[:1],
                    }
                ]
            return result

    meetings = MeetingStore(tmp_path / "meetings")
    meeting_id = meetings.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {
            "id": i,
            "start": float(i * 2),
            "end": float(i * 2 + 1),
            "text": f"Nhóm FPT sẽ thử nghiệm hạng mục {i} trong bản đầu.",
        }
        for i in range(1, 5)
    ]
    TranscriptStore(meetings).save_run(meeting_id, run_id, model, "vi", {"duration": 10}, segments)
    fake = TruncatingOllama()
    version = LocalMinutesJobs(meetings, tmp_path / "llm.json", fake)._generate(
        meeting_id, "general"
    )
    saved = MinutesStore(meetings).read_version(meeting_id, version)
    actions = saved["content"]["domain"]["sections"]["project_actions"]
    assert {source["segment_id"] for action in actions for source in action["sources"]} == {
        1,
        2,
        3,
        4,
    }
    assert len([prompt for prompt in fake.prompts if "form biên bản DENSO" in prompt]) == 3


def test_single_long_segment_splits_without_losing_source_id():
    row = {"id": 7, "text": "Thông tin kho cần kiểm tra. " * 80}
    left, right = _split_chunk([row])
    assert left[0]["id"] == right[0]["id"] == 7
    assert left[0]["text"] + " " + right[0]["text"] == row["text"].strip()


def test_echoed_transcript_is_rejected_as_a_semantic_summary():
    with pytest.raises(OllamaError, match="copied"):
        _summary(
            {
                "summary": "Quầy bán lẻ cần có chức năng quét mã vạch và in hóa đơn.",
                "source_ids": [1],
            },
            {1},
            "[1] Quầy bán lẻ cần có chức năng quét mã vạch và in hóa đơn.",
        )


def test_summary_may_start_with_source_phrase_if_rest_is_new():
    source = "Quầy bán lẻ cần có chức năng quét mã vạch và in hóa đơn."
    summary = (
        "Quầy bán lẻ cần có chức năng quét mã vạch; nhóm cũng sẽ kiểm tra "
        "phạm vi báo cáo doanh thu theo ca."
    )
    result = _summary({"summary": summary, "source_ids": [1]}, {1}, f"[1] {source}")
    assert result["text"] == summary


def test_bridge_starts_background_local_minutes_and_returns_saved_version(tmp_path):
    app = BridgeApplication(tmp_path)
    app.local_minutes.client = FakeOllama()
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
        [{"id": 1, "start": 0.0, "end": 2.0, "text": "Đã thống nhất thử nghiệm."}],
    )
    assert call(app, "llm.availability")["ready"] is True
    assert call(app, "minutes.generateLocalStart", meetingId=meeting_id, meetingType="general") == {
        "started": True
    }
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = call(app, "minutes.localStatus")
        if status["state"] != "running":
            break
        time.sleep(0.02)
    assert status["state"] == "completed", status
    assert (
        call(app, "minutes.read", meetingId=meeting_id, versionId=status["versionId"])["version"][
            "manifest"
        ]["origin"]
        == "local_llm"
    )


def test_long_transcript_is_summarized_in_chunks_then_consolidated(tmp_path):
    from fahmm.storage import MeetingStore
    from fahmm.transcripts import TranscriptStore

    class ChunkAwareOllama(FakeOllama):
        def generate(self, model, prompt, *, form=False):
            self.prompts.append(prompt)
            first_id = int(re.search(r"\[(\d+)\]", prompt).group(1))
            text = (
                "Toàn cuộc họp chốt các bước thử nghiệm hệ thống bán hàng."
                if "các tóm tắt từng phần" in prompt
                else "Nhóm bàn về quy trình bán hàng và thống nhất phạm vi thử nghiệm."
            )
            return {"summary": text, "source_ids": [first_id], **({"items": []} if form else {})}

    meetings = MeetingStore(tmp_path / "meetings")
    meeting_id = meetings.create({})
    run_id = uuid.uuid4().hex
    model = InstalledModel(uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, tmp_path)
    segments = [
        {
            "id": i,
            "start": float(i * 20),
            "end": float(i * 20 + 10),
            "text": f"Yêu cầu bán hàng và tồn kho mục {i}." * 4,
        }
        for i in range(1, 101)
    ]
    TranscriptStore(meetings).save_run(
        meeting_id, run_id, model, "vi", {"duration": 2010}, segments
    )
    fake = ChunkAwareOllama()
    version = LocalMinutesJobs(meetings, tmp_path / "llm.json", fake)._generate(
        meeting_id, "general"
    )
    assert len(fake.prompts) >= 3
    saved = MinutesStore(meetings).read_version(meeting_id, version)
    sources = saved["content"]["domain"]["sections"]["summary"][0]["sources"]
    assert sources and all(source["segment_id"] in range(1, 101) for source in sources)
