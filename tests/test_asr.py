import multiprocessing
import os
import queue
import socket
from pathlib import Path

import pytest

from fahmm.asr_worker import run_asr_worker
from fahmm.models import ModelManager


def blocked_worker(audio_path, model_path, language, output, cancel):
    def no_network(*args, **kwargs):
        raise AssertionError("ASR attempted a network connection")

    socket.socket.connect = no_network
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("HF_TOKEN", None)
    run_asr_worker(audio_path, model_path, language, output, cancel)


def test_spawned_worker_transcribes_local_speech_without_network():
    selected = ModelManager().selected()
    model_path = os.environ.get("FAHMM_TEST_MODEL_DIR") or (
        str(selected.path) if selected else None
    )
    if not model_path:
        pytest.skip("Set FAHMM_TEST_MODEL_DIR to run the real offline ASR smoke test")
    context = multiprocessing.get_context("spawn")
    output = context.Queue(maxsize=16)
    cancel = context.Event()
    fixture = Path(__file__).parent / "fixtures" / "jfk.flac"
    process = context.Process(
        target=blocked_worker,
        args=(str(fixture), model_path, "en", output, cancel),
    )
    process.start()
    messages = []
    try:
        for _ in range(20):
            try:
                item = output.get(timeout=3)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            messages.append(item)
            if item["type"] in ("completed", "error"):
                break
        process.join(timeout=10)
        assert not process.is_alive()
        assert process.exitcode == 0
        assert messages[0]["type"] == "started"
        assert messages[-1]["type"] == "completed"
        assert any(
            "fellow Americans" in item["segment"]["text"]
            for item in messages
            if item["type"] == "segment"
        )
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
