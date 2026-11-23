import time

import pytest
import requests
from openpyxl import load_workbook

from fahmm.reports.llm import HTTP as REPORT_HTTP
from fahmm.reports.llm import Extracted
from fahmm.reports.service import ReportService


class Meetings:
    def metadata(self, meeting_id):
        return {"name": "Cuộc họp mẫu"}


class Transcripts:
    def active_run(self, meeting_id):
        return {"working": [{"start": 12, "text": "Người phụ trách: Lan."}]}


def test_report_sources_provenance_export_and_no_overwrite(tmp_path, monkeypatch):
    source = tmp_path / "report.txt"
    source.write_text("Người phụ trách: Lan.", encoding="utf-8")
    service = ReportService(Meetings(), Transcripts(), tmp_path)
    monkeypatch.setattr(service, "ensure_server", lambda: None)
    monkeypatch.setattr(service, "_available", lambda: ["qwen3.5:2b-q4_K_M"])
    monkeypatch.setattr(
        "fahmm.reports.llm.HTTP.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError()),
    )
    unloaded = []
    monkeypatch.setattr("fahmm.reports.llm.running", lambda: ["qwen3.5:2b-q4_K_M"])
    monkeypatch.setattr("fahmm.reports.llm.unload", unloaded.append)

    def fake_extract(model, text, **kwargs):
        return Extracted.model_validate(
            {
                "facts": [
                    {"field": "phu_trach", "value": "Lan", "quote": "Người phụ trách: Lan."},
                    {"field": "deadline", "value": "2027", "quote": "không có"},
                ]
            }
        ), {"eval_count": 3, "eval_duration": 1_000_000_000}

    monkeypatch.setattr("fahmm.reports.pipeline.extract", fake_extract)
    assert len(service.add_file(str(source))["files"]) == 1
    assert len(service.add_transcript("meeting-id")["files"]) == 2
    with pytest.raises(ValueError):
        service.add_file(str(source))
    service.start("qwen3.5:2b-q4_K_M", "")
    deadline = time.monotonic() + 5
    while service.status()["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    status = service.status()
    assert status["state"] == "completed"
    assert unloaded == ["qwen3.5:2b-q4_K_M"]
    assert status["facts"] == 2
    assert "Phiên âm - Cuộc họp mẫu" in status["preview"]
    assert "Trích dẫn không khớp" in status["preview"]
    export = tmp_path / "out"
    export.mkdir()
    service.export(str(export))
    workbook = load_workbook(export / "Bang_Tong_Hop.xlsx")
    assert workbook.sheetnames == ["Tổng hợp", "Chi tiết nguồn", "Cần kiểm tra"]
    with pytest.raises(FileExistsError):
        service.export(str(export))


def test_reject_invalid_model_or_unselected_source(tmp_path, monkeypatch):
    service = ReportService(Meetings(), Transcripts(), tmp_path)
    assert REPORT_HTTP.trust_env is False
    with pytest.raises(ValueError):
        service.add_file("relative.txt")
    with pytest.raises(ValueError):
        service.start("remote:cloud", "")


def test_refuses_to_load_a_second_ollama_model(tmp_path, monkeypatch):
    service = ReportService(Meetings(), Transcripts(), tmp_path)
    monkeypatch.setattr(service, "ensure_server", lambda: None)
    monkeypatch.setattr(service, "_available", lambda: ["qwen3.5:2b-q4_K_M"])

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "someone-elses-model"}]}

    monkeypatch.setattr("fahmm.reports.llm.HTTP.get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="11434"):
        service.start("qwen3.5:2b-q4_K_M", "")
