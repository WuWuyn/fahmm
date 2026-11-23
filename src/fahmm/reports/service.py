"""Report jobs use only selected local files and a dedicated loopback Ollama."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import requests

from fahmm.reports import llm
from fahmm.reports.documents import Passage
from fahmm.reports.export import export_all, report_text
from fahmm.reports.pipeline import run_pipeline
from fahmm.reports.settings import HOST, MODELS


class ReportService:
    def __init__(self, meetings, transcripts, data_root: Path):
        self.meetings, self.transcripts, self.data_root = meetings, transcripts, data_root
        self._files: dict[str, Path | Passage] = {}
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._state = "idle"
        self._detail = ""
        self._progress = 0.0
        self._result = None
        self._form = ""

    def _available(self):
        try:
            return llm.tags()
        except requests.RequestException:
            return []

    def _model_directory(self):
        existing = Path(r"D:\fahm\ReportAI_Local_Test\models")
        return Path(
            os.environ.get("FAHMM_REPORT_MODEL_DIR")
            or (str(existing) if existing.is_dir() else str(self.data_root / "report-models"))
        )

    def ensure_server(self):
        try:
            llm.HTTP.get(HOST + "/api/version", timeout=2).raise_for_status()
            return
        except requests.RequestException:
            pass
        executable = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if not executable.is_file():
            raise RuntimeError("Không tìm thấy Ollama. Hãy cài Ollama cho Windows.")
        model_dir = self._model_directory()
        model_dir.mkdir(parents=True, exist_ok=True)
        env = dict(
            os.environ,
            OLLAMA_HOST="127.0.0.1:11435",
            OLLAMA_MODELS=str(model_dir),
            OLLAMA_NUM_PARALLEL="1",
            OLLAMA_MAX_LOADED_MODELS="1",
        )
        subprocess.Popen(
            [str(executable), "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(20):
            time.sleep(0.5)
            try:
                llm.HTTP.get(HOST + "/api/version", timeout=1).raise_for_status()
                return
            except requests.RequestException:
                pass
        raise RuntimeError("Không khởi động được Ollama tại cổng 11435.")

    def models(self):
        self.ensure_server()
        installed = self._available()
        return {
            "models": [
                {"id": model, "installed": model.lower() in {item.lower() for item in installed}}
                for model in MODELS
            ]
        }

    def _check_idle(self):
        if self._state == "running":
            raise ValueError("Đang xử lý, hãy chờ hoặc hủy tác vụ trước.")

    def add_file(self, path: str):
        item = Path(path)
        if (
            not item.is_absolute()
            or not item.is_file()
            or item.suffix.lower() not in {".pdf", ".docx", ".xlsx", ".txt", ".md"}
        ):
            raise ValueError("Chọn tệp PDF, DOCX, XLSX, TXT hoặc Markdown hợp lệ.")
        with self._lock:
            self._check_idle()
            if any(
                (p.file if isinstance(p, Passage) else p.name).casefold() == item.name.casefold()
                for p in self._files.values()
            ):
                raise ValueError("Đã có tài liệu cùng tên; hãy đổi tên trước khi thêm.")
            self._files[uuid.uuid4().hex] = item.resolve()
            self._result = None
            self._state = "idle"
            self._detail = ""
            self._progress = 0
        return self.status()

    def add_transcript(self, meeting_id: str):
        run = self.transcripts.active_run(meeting_id)
        if not run:
            raise ValueError("Cuộc họp chưa có bản phiên âm đã lưu.")
        metadata = self.meetings.metadata(meeting_id)
        lines = [
            f"[{float(s.get('start', 0)):.1f}s] {s['text']}"
            for s in run["working"]
            if isinstance(s.get("text"), str) and s["text"].strip()
        ]
        if not lines:
            raise ValueError("Bản phiên âm đang trống.")
        name = f"Phiên âm - {metadata.get('name', meeting_id)} [{meeting_id[:8]}]"
        with self._lock:
            self._check_idle()
            if any(isinstance(p, Passage) and p.file == name for p in self._files.values()):
                raise ValueError("Bản phiên âm này đã được thêm.")
            self._files[uuid.uuid4().hex] = Passage(
                name, "Bản phiên âm có mốc thời gian", "\n".join(lines)
            )
            self._result = None
            self._state = "idle"
            self._detail = ""
            self._progress = 0
        return self.status()

    def clear(self):
        with self._lock:
            self._check_idle()
            self._files.clear()
            self._result = None
            self._state = "idle"
            self._detail = ""
            self._progress = 0
        return self.status()

    def pull(self, model: str):
        if model not in MODELS:
            raise ValueError("Model không hợp lệ.")
        self.ensure_server()
        model_dir = self._model_directory()
        model_dir.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(model_dir).free < 12 * 1024**3:
            raise ValueError("Ổ lưu model cần ít nhất 12 GB trống trước khi tải.")
        with self._lock:
            self._check_idle()
            self._state = "running"
            self._detail = "Đang tải model…"
            self._progress = 0
            self._cancel.clear()
        threading.Thread(target=self._pull, args=(model,), daemon=True).start()

    def _pull(self, model):
        try:
            with llm.HTTP.post(
                HOST + "/api/pull",
                json={"model": model, "stream": True},
                stream=True,
                timeout=(10, 600),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if self._cancel.is_set():
                        with self._lock:
                            self._state = "cancelled"
                            self._detail = "Đã hủy tải model."
                        return
                    if not line:
                        continue
                    item = __import__("json").loads(line)
                    if "error" in item:
                        raise RuntimeError(item["error"])
                    with self._lock:
                        self._detail = str(item.get("status", "Đang tải model…"))[:200]
                        if item.get("total"):
                            self._progress = item.get("completed", 0) / item["total"]
            with self._lock:
                self._state = "idle"
                self._detail = "Đã tải model."
                self._progress = 1
        except Exception as exc:
            with self._lock:
                self._state = "failed"
                self._detail = str(exc)[:300]

    def status(self):
        with self._lock:
            result = self._result
            return {
                "state": self._state,
                "detail": self._detail,
                "progress": self._progress,
                "files": [
                    {"id": k, "name": v.file if isinstance(v, Passage) else v.name}
                    for k, v in self._files.items()
                ],
                "preview": report_text(result, self._form)[:80000] if result else "",
                "metrics": result["metrics"] if result else {},
                "facts": len(result["facts"]) if result else 0,
                "warnings": len(result["warnings"]) if result else 0,
            }

    def start(self, model: str, form: str):
        if model not in MODELS or len(form) > 10000:
            raise ValueError("Model hoặc form không hợp lệ.")
        self.ensure_server()
        if model.lower() not in {m.lower() for m in self._available()}:
            raise ValueError("Model chưa được tải trong kho báo cáo.")
        try:
            other = llm.HTTP.get("http://127.0.0.1:11434/api/ps", timeout=2)
            other.raise_for_status()
            if other.json().get("models"):
                raise ValueError(
                    "Một model Ollama khác đang hoạt động ở cổng 11434. Hãy giải phóng model đó trước khi tạo báo cáo."
                )
        except requests.RequestException:
            pass
        with self._lock:
            self._check_idle()
            if not self._files:
                raise ValueError("Hãy thêm ít nhất một tài liệu hoặc bản phiên âm.")
            files = list(self._files.values())
            self._result = None
            self._form = form
            self._cancel.clear()
            self._state = "running"
            self._detail = "Đang xử lý…"
            self._progress = 0
        threading.Thread(target=self._run, args=(files, model), daemon=True).start()

    def _run(self, files, model):
        def progress(index, total, detail):
            with self._lock:
                self._detail = detail
                self._progress = index / max(total, 1)

        result = None
        unload_failed = False
        try:
            result = run_pipeline(files, model, progress, self._cancel)
            state = "completed" if result["facts"] else "failed"
            detail = (
                "Hoàn tất; hãy kiểm tra cảnh báo và nguồn."
                if result["facts"]
                else "Không có dữ kiện hợp lệ; hãy xem cảnh báo."
            )
        except InterruptedError:
            state, detail = "cancelled", "Đã hủy."
        except Exception as exc:
            state, detail = "failed", str(exc)[:300]
        finally:
            try:
                if model in llm.running():
                    llm.unload(model)
            except Exception:
                unload_failed = True
        with self._lock:
            if unload_failed:
                detail += " Không thể tự giải phóng model; hãy kiểm tra Ollama."
            self._result = result
            self._state = state
            self._detail = detail
            if result is not None:
                self._progress = 1.0

    def cancel(self):
        self._cancel.set()

    def export(self, directory: str):
        path = Path(directory)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Chọn thư mục xuất hợp lệ.")
        with self._lock:
            if not self._result or self._state != "completed":
                raise ValueError("Chưa có báo cáo để xuất.")
            export_all(self._result, path, self._form)
        return {"saved": True}
