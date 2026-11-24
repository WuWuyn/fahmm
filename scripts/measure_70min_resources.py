"""Measure a synthetic 70-minute meeting through the frozen local fahmm sidecar."""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
import wave
from datetime import datetime
from pathlib import Path

import av
import numpy as np
import psutil

if __package__:
    from .benchmark_memory import MIB, MemoryGuard, MemoryPolicy, MemoryWatchdog
else:
    from benchmark_memory import MIB, MemoryGuard, MemoryPolicy, MemoryWatchdog

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = Path(
    os.environ.get(
        "FAHMM_BENCHMARK_SIDECAR", str(ROOT / ".build/Fahmm_So_Sanh_Model/fahmm-sidecar.exe")
    )
)
USER_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "fahmm"
SOURCE = USER_ROOT / "demo/retail-requirements-60m.mp3"
RUN = (
    ROOT
    / ".build"
    / ("benchmark-70m-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
)
TARGET_SAMPLES = 70 * 60 * 16000
NUMBER_CPUS = psutil.cpu_count() or 1
MEMORY_POLICY = MemoryPolicy()


def _available_memory() -> int | None:
    try:
        return psutil.virtual_memory().available
    except (OSError, psutil.Error):
        return None


def _stop_owned_sidecar(root: psutil.Process, known_children=()) -> None:
    """Stop only the sidecar process created by this benchmark and its descendants."""
    children = list(known_children)
    try:
        if root.is_running():
            children.extend(root.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    try:
        for child in reversed(children):
            try:
                if child.is_running():
                    child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if root.is_running():
            root.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return


def prepare_audio(destination: Path) -> dict:
    total = 0
    non_silent = 0
    frame_count = 0
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        while total < TARGET_SAMPLES:
            with av.open(str(SOURCE)) as audio:
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                for frame in audio.decode(audio=0):
                    for converted in resampler.resample(frame):
                        length = min(converted.samples, TARGET_SAMPLES - total)
                        if length <= 0:
                            break
                        data = bytes(converted.planes[0])[: length * 2]
                        output.writeframesraw(data)
                        values = np.frombuffer(data, dtype="<i2").astype(np.float32)
                        if values.size and float(np.sqrt(np.mean(values * values))) >= 327.68:
                            non_silent += 1
                        frame_count += 1
                        total += length
                    if total >= TARGET_SAMPLES:
                        break
    return {
        "seconds": total / 16000,
        "non_silent_audio_frames_pct": round(100 * non_silent / max(1, frame_count), 1),
        "activity_note": "rough RMS threshold -40 dB, not speech detection",
    }


def find_ollama_server() -> int:
    for item in psutil.net_connections(kind="tcp"):
        if item.status == "LISTEN" and item.laddr.port == 11434 and item.pid:
            return item.pid
    raise RuntimeError("Ollama trên cổng 11434 chưa chạy.")


class Monitor:
    def __init__(self, sidecar_pid: int, ollama_pid: int, output: Path):
        self.sidecar_pid, self.ollama_pid = sidecar_pid, ollama_pid
        # The psutil object retains creation identity, preventing PID reuse from
        # turning a later abort into a signal to a different application.
        self.owned_sidecar = psutil.Process(sidecar_pid)
        self.ollama = psutil.Process(ollama_pid)
        self._owned_lock = threading.Lock()
        self._owned_children = {}
        self.output = output
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.phase = None
        self.samples: list[dict] = []
        self.last_cpu: dict[tuple[int, float], tuple[float, float]] = {}
        self.start_time = time.monotonic()
        self.gpu = None
        self.memory_abort = False
        self.memory_abort_reason = None
        self.watchdog = MemoryWatchdog(MEMORY_POLICY, _available_memory, self._abort_owned)
        self.thread = threading.Thread(target=self.run, daemon=True)
        psutil.cpu_percent(None)
        self.watchdog.start()
        self.thread.start()

    def _abort_owned(self, reason: str) -> None:
        self.memory_abort_reason = reason
        self.memory_abort = True
        with self._owned_lock:
            children = list(self._owned_children.values())
        _stop_owned_sidecar(self.owned_sidecar, children)

    def _remember_owned(self, children) -> None:
        with self._owned_lock:
            for child in children:
                try:
                    self._owned_children[(child.pid, child.create_time())] = child
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

    def set_phase(self, phase):
        with self.lock:
            self.phase = phase
            self.last_cpu = {}

    def run(self):
        tick = 0
        with self.output.open("w", encoding="utf-8") as log:
            while not self.stop_event.wait(1):
                with self.lock:
                    phase = self.phase
                    if not phase:
                        continue
                    now = time.monotonic()
                    roots = [self.sidecar_pid] + ([self.ollama_pid] if phase == "minutes" else [])
                    procs = {}
                    for root in roots:
                        try:
                            parent = self.owned_sidecar if root == self.sidecar_pid else self.ollama
                            if not parent.is_running():
                                continue
                            descendants = parent.children(recursive=True)
                            if root == self.sidecar_pid:
                                self._remember_owned(descendants)
                            for proc in [parent, *descendants]:
                                procs[proc.pid] = proc
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    rss = 0
                    cpu_cores_percent = 0.0
                    observed = []
                    for proc in procs.values():
                        try:
                            key = (proc.pid, proc.create_time())
                            cpu_times = proc.cpu_times()
                            cpu_seconds = cpu_times.user + cpu_times.system
                            previous = self.last_cpu.get(key)
                            if previous and now > previous[0]:
                                cpu_cores_percent += (
                                    max(0, cpu_seconds - previous[1]) / (now - previous[0]) * 100
                                )
                            self.last_cpu[key] = (now, cpu_seconds)
                            rss += proc.memory_info().rss
                            observed.append(proc.name())
                        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
                            pass
                    tick += 1
                    if tick % 5 == 1:
                        try:
                            gpu = subprocess.check_output(
                                [
                                    "nvidia-smi",
                                    "--query-gpu=memory.used,utilization.gpu",
                                    "--format=csv,noheader,nounits",
                                ],
                                timeout=3,
                                text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            parts = gpu.strip().splitlines()[0].split(",")
                            self.gpu = {
                                "used_mb": float(parts[0]),
                                "utilization_pct": float(parts[1]),
                            }
                        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
                            self.gpu = None
                    memory = psutil.virtual_memory()
                    sample = {
                        "phase": phase,
                        "elapsed": round(now - self.start_time, 2),
                        "process_working_set_mb": round(rss / 1024**2, 2),
                        "process_cpu_one_core_pct": round(cpu_cores_percent, 2),
                        "process_cpu_system_pct": round(cpu_cores_percent / NUMBER_CPUS, 2),
                        "system_cpu_pct": psutil.cpu_percent(None),
                        "system_available_mb": round(memory.available / 1024**2, 2),
                        "system_used_mb": round((memory.total - memory.available) / 1024**2, 2),
                        "process_names": observed,
                        "gpu": self.gpu,
                    }
                    self.samples.append(sample)
                    log.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    log.flush()

    def summary(self, phase, seconds):
        with self.lock:
            rows = [x for x in self.samples if x["phase"] == phase]
        if not rows:
            return {"seconds": round(seconds, 2), "samples": 0}
        avg = lambda key: round(sum(x[key] for x in rows) / len(rows), 2)
        gpu = [x["gpu"] for x in rows if x["gpu"] is not None]
        return {
            "seconds": round(seconds, 2),
            "samples": len(rows),
            "working_set_peak_mb": max(x["process_working_set_mb"] for x in rows),
            "working_set_avg_mb": avg("process_working_set_mb"),
            "cpu_avg_pct_one_core": avg("process_cpu_one_core_pct"),
            "cpu_peak_pct_one_core": max(x["process_cpu_one_core_pct"] for x in rows),
            "cpu_avg_pct_machine": avg("process_cpu_system_pct"),
            "cpu_peak_pct_machine": max(x["process_cpu_system_pct"] for x in rows),
            "system_cpu_avg_pct": avg("system_cpu_pct"),
            "system_available_min_mb": min(x["system_available_mb"] for x in rows),
            "gpu_system_used_peak_mb": max((x["used_mb"] for x in gpu), default=None),
            "gpu_system_utilization_peak_pct": max(
                (x["utilization_pct"] for x in gpu), default=None
            ),
        }

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)
        self.watchdog.stop()


def main():
    if not SIDECAR.is_file() or not SOURCE.is_file():
        raise RuntimeError("Thiếu bộ xử lý fahmm hoặc âm thanh mẫu 60 phút.")
    index = json.loads((USER_ROOT / "models/index.json").read_text(encoding="utf-8"))
    model_id = index["selected"]
    selected = index["installations"][model_id]
    model_source = USER_ROOT / "models/installed" / model_id
    local_model = json.loads((USER_ROOT / "local_llm.json").read_text(encoding="utf-8"))["model"]
    if (
        not model_source.is_dir()
        or not isinstance(local_model, str)
        or local_model.endswith(":cloud")
    ):
        raise RuntimeError("Model hiện chọn không hợp lệ hoặc không phải model cục bộ.")
    wait_started = time.monotonic()
    last_notice = 0
    while True:
        available = _available_memory()
        reason = MemoryGuard(MEMORY_POLICY).preflight(available)
        if reason is None:
            break
        if reason == "memory_sample_unavailable":
            raise MemoryError("Không đọc được RAM khả dụng; không bắt đầu benchmark.")
        if time.monotonic() - wait_started > 900:
            raise MemoryError("Không đủ RAM khả dụng sau 15 phút chờ.")
        if time.monotonic() - last_notice >= 30:
            print(
                f"Chờ RAM: còn {available / MIB:.0f} MiB, cần {MEMORY_POLICY.start_mib} MiB.",
                flush=True,
            )
            last_notice = time.monotonic()
        time.sleep(2)
    RUN.mkdir(parents=True)
    if shutil.disk_usage(RUN).free < selected["bytes"] + 1024**3:
        raise RuntimeError("Không đủ dung lượng ổ D cho bản sao model và âm thanh thử.")
    print("Đầu ra:", RUN, flush=True)
    print("Đang tạo âm thanh tổng hợp 70 phút từ mẫu 60 phút…", flush=True)
    audio_path = RUN / "synthetic-meeting-70m.wav"
    audio_info = prepare_audio(audio_path)
    print("Âm thanh:", json.dumps(audio_info, ensure_ascii=False), flush=True)
    print("Đang tạo bản sao model phiên âm trong thư mục thử…", flush=True)
    appdata = RUN / "appdata"
    models = appdata / "fahmm/models"
    shutil.copytree(model_source, models / "installed" / model_id)
    (models / "index.json").write_text(
        json.dumps(
            {"schema_version": 1, "selected": model_id, "installations": {model_id: selected}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (appdata / "fahmm/local_llm.json").write_text(
        json.dumps({"model": local_model}), encoding="utf-8"
    )
    ollama_pid = find_ollama_server()
    if MemoryGuard(MEMORY_POLICY).preflight(_available_memory()) is not None:
        raise MemoryError("RAM khả dụng đã giảm; không khởi chạy bộ xử lý.")
    env = dict(os.environ, LOCALAPPDATA=str(appdata), TEMP=str(RUN), TMP=str(RUN))
    stderr = (RUN / "sidecar.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(SIDECAR)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
        encoding="utf-8",
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    sequence = 0
    monitor = None
    replies: queue.Queue[str] = queue.Queue(maxsize=4)
    report = {
        "input": audio_info,
        "asr_model": selected["repository"],
        "minutes_model": local_model,
        "logical_cpus": NUMBER_CPUS,
        "source_kind": "synthetic 60 minutes + repeated first 10 minutes",
        "scope": "frozen sidecar process tree; local Ollama server tree during minutes; desktop UI excluded",
        "memory_guard": MEMORY_POLICY.as_dict(),
    }

    def pump_replies():
        try:
            while True:
                line = process.stdout.readline()
                replies.put(line, timeout=2)
                if not line:
                    return
        except (OSError, ValueError, queue.Full):
            return

    reader = threading.Thread(target=pump_replies, daemon=True)
    reader.start()

    def save():
        (RUN / "results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def call(op, params):
        nonlocal sequence
        sequence += 1
        frame = {"v": 1, "kind": "request", "id": str(sequence), "op": op, "params": params}
        process.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 120
        while True:
            if monitor is not None and monitor.memory_abort:
                raise MemoryError(
                    f"Benchmark stopped by RAM watchdog: {monitor.memory_abort_reason}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("Bộ xử lý không phản hồi trong thời gian cho phép.")
            try:
                line = replies.get(timeout=MEMORY_POLICY.sample_seconds)
                break
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("Bộ xử lý đã đóng trước khi phản hồi.") from None
        if not line:
            raise RuntimeError("Bộ xử lý đóng trước khi phản hồi.")
        result = json.loads(line)
        if result.get("kind") != "response":
            raise RuntimeError(f"{op}: {result.get('error')}")
        return result["result"]

    try:
        # The watchdog starts immediately, before handshake, import or inference.
        monitor = Monitor(process.pid, ollama_pid, RUN / "samples.jsonl")
        monitor.set_phase("startup")
        call("session.hello", {"versions": [1]})
        availability = call("llm.availability", {})
        if not availability.get("ready") or availability.get("selectedModel") != local_model:
            raise RuntimeError("Model AI tạo biên bản hiện chọn chưa sẵn sàng.")
        meeting = call("meeting.import", {"nativePath": str(audio_path)})["meetingId"]
        print(
            "Đã sẵn sàng; phiên âm:", selected["repository"], "| biên bản:", local_model, flush=True
        )
        monitor.set_phase("transcription")
        start = time.monotonic()
        call("asr.start", {"meetingId": meeting, "modelId": model_id, "language": "vi"})
        last_message = 0
        while True:
            time.sleep(2)
            state = call("asr.status", {})
            if time.monotonic() - last_message >= 30:
                print(
                    "Phiên âm:",
                    state["state"],
                    "tiến độ:",
                    state["progress"],
                    "đoạn:",
                    state["segmentCount"],
                    flush=True,
                )
                last_message = time.monotonic()
            if state["state"] not in ("loading", "running", "cancelling"):
                break
        report["transcription"] = {
            **monitor.summary("transcription", time.monotonic() - start),
            "state": state["state"],
            "segment_count": state["segmentCount"],
            "error": state.get("error"),
        }
        save()
        print(
            "Kết quả phiên âm:", json.dumps(report["transcription"], ensure_ascii=False), flush=True
        )
        if state["state"] != "completed":
            raise RuntimeError("Phiên âm chưa hoàn tất.")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:11434/api/ps", timeout=5) as response:
            active = json.load(response).get("models", [])
        if any(str(item.get("name", "")).casefold() != local_model.casefold() for item in active):
            raise RuntimeError(
                "Một model Ollama khác đang chạy; không thay đổi model đang dùng của bạn."
            )
        monitor.set_phase("minutes")
        start = time.monotonic()
        started = call(
            "minutes.generateLocalStart", {"meetingId": meeting, "meetingType": "general"}
        )
        job_id = started.get("jobId")
        last_message = 0
        while True:
            time.sleep(2)
            state = call("minutes.localStatus", {})
            if time.monotonic() - last_message >= 30:
                print("Biên bản:", state["state"], "tiến độ:", state["progress"], flush=True)
                last_message = time.monotonic()
            if monitor.memory_abort:
                report["minutes"] = {
                    **monitor.summary("minutes", time.monotonic() - start),
                    "state": state["state"],
                    "job_id": job_id,
                    "error": state.get("error"),
                }
                raise MemoryError(f"Dừng thử do RAM: {monitor.memory_abort_reason}")
            if state["state"] not in ("running", "cancelling", "saving"):
                break
        report["minutes"] = {
            **monitor.summary("minutes", time.monotonic() - start),
            "state": state["state"],
            "job_id": job_id,
            "error": state.get("error"),
        }
        if isinstance(job_id, str) and re.fullmatch(r"[0-9a-f]{32}", job_id):
            metric_path = (
                appdata
                / "fahmm"
                / "meetings"
                / meeting
                / "minutes"
                / "ai-metrics"
                / f"{job_id}.json"
            )
            if metric_path.is_file():
                report["minutes"]["runtime_metrics"] = json.loads(
                    metric_path.read_text(encoding="utf-8")
                )
        save()
        print("Kết quả biên bản:", json.dumps(report["minutes"], ensure_ascii=False), flush=True)
        if state["state"] != "completed":
            raise RuntimeError("Chưa tạo được biên bản.")
        report["completed"] = True
        save()
    except Exception as exc:
        report["completed"] = False
        report["error"] = str(exc)
        if monitor is not None:
            report["memory_guard"]["stop_reason"] = monitor.memory_abort_reason
            minimum = monitor.watchdog.minimum_available
            report["memory_guard"]["minimum_sampled_available_mib"] = (
                round(minimum / MIB, 1) if minimum is not None else None
            )
        save()
        raise
    finally:
        if process.stdin:
            with contextlib.suppress(BrokenPipeError, OSError):
                process.stdin.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if monitor is not None:
                with monitor._owned_lock:
                    children = list(monitor._owned_children.values())
                _stop_owned_sidecar(monitor.owned_sidecar, children)
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        if monitor:
            with monitor._owned_lock:
                children = list(monitor._owned_children.values())
            _stop_owned_sidecar(monitor.owned_sidecar, children)
            monitor.stop()
            minimum = monitor.watchdog.minimum_available
            report["memory_guard"]["stop_reason"] = monitor.memory_abort_reason
            report["memory_guard"]["minimum_sampled_available_mib"] = (
                round(minimum / MIB, 1) if minimum is not None else None
            )
            save()
        reader.join(timeout=1)
        stderr.close()


if __name__ == "__main__":
    main()
