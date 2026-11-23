import multiprocessing
import os
import queue
import socket
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fahmm.asr import WhisperASRBackend, _runtime_settings
from fahmm.asr_worker import run_asr_worker
from fahmm.models import ModelManager


def blocked_worker(audio_path, model_path, language, output, cancel, start_seconds=0.0):
    def no_network(*args, **kwargs):
        raise AssertionError("ASR attempted a network connection")

    socket.socket.connect = no_network
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("HF_TOKEN", None)
    run_asr_worker(audio_path, model_path, language, output, cancel, start_seconds)


def test_asr_decodes_selected_range_to_end_and_keeps_source_timestamps(tmp_path, monkeypatch):
    for variable in ("FAHMM_ASR_DEVICE", "FAHMM_ASR_COMPUTE_TYPE", "FAHMM_ASR_BEAM_SIZE"):
        monkeypatch.delenv(variable, raising=False)
    audio_path = tmp_path / "selected.wav"
    audio_path.write_bytes(b"local audio fixture")
    monkeypatch.setattr("fahmm.asr.validate_model_dir", lambda path: None)
    monkeypatch.setattr(
        "faster_whisper.audio.decode_audio", lambda path: np.ones(4 * 16_000, dtype=np.float32)
    )
    observed = []

    class FakeModel:
        def __init__(self, path, **kwargs):
            assert kwargs["local_files_only"] is True
            assert kwargs["device"] == "cpu"
            assert kwargs["compute_type"] == "int8"

        def transcribe(self, audio, **kwargs):
            assert kwargs["vad_filter"] is True
            assert kwargs["beam_size"] == 5
            observed.append((len(audio), kwargs["language"]))
            return iter(
                [
                    SimpleNamespace(id=1, start=0.0, end=1.0, text=" first "),
                    SimpleNamespace(id=2, start=2.0, end=29.98, text=" last "),
                ]
            ), SimpleNamespace(language="vi", duration=3.0)

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    segments, info = WhisperASRBackend().transcribe(audio_path, tmp_path, "vi", 1.0)
    assert observed == [(3 * 16_000, "vi")]
    assert [(s.start, s.end, s.text) for s in segments] == [
        (1.0, 2.0, "first"),
        (3.0, 4.0, "last"),
    ]
    assert info.duration == 4.0


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, ("cpu", "int8", 5)),
        ({"FAHMM_ASR_BEAM_SIZE": "1"}, ("cpu", "int8", 1)),
        ({"FAHMM_ASR_DEVICE": "cuda"}, ("cuda", "int8_float16", 5)),
        (
            {
                "FAHMM_ASR_DEVICE": "CUDA",
                "FAHMM_ASR_COMPUTE_TYPE": "int8_float16",
                "FAHMM_ASR_BEAM_SIZE": "1",
            },
            ("cuda", "int8_float16", 1),
        ),
    ],
)
def test_asr_runtime_settings_are_explicit_and_safe(monkeypatch, settings, expected):
    for variable in ("FAHMM_ASR_DEVICE", "FAHMM_ASR_COMPUTE_TYPE", "FAHMM_ASR_BEAM_SIZE"):
        monkeypatch.delenv(variable, raising=False)
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    assert _runtime_settings() == expected


@pytest.mark.parametrize(
    ("settings", "error"),
    [
        ({"FAHMM_ASR_DEVICE": "gpu"}, "FAHMM_ASR_DEVICE"),
        ({"FAHMM_ASR_COMPUTE_TYPE": "int8_float16"}, "FAHMM_ASR_COMPUTE_TYPE"),
        (
            {"FAHMM_ASR_DEVICE": "cuda", "FAHMM_ASR_COMPUTE_TYPE": "float32"},
            "FAHMM_ASR_COMPUTE_TYPE",
        ),
        ({"FAHMM_ASR_BEAM_SIZE": "0"}, "FAHMM_ASR_BEAM_SIZE"),
        ({"FAHMM_ASR_BEAM_SIZE": "11"}, "FAHMM_ASR_BEAM_SIZE"),
        ({"FAHMM_ASR_BEAM_SIZE": "fast"}, "FAHMM_ASR_BEAM_SIZE"),
    ],
)
def test_asr_rejects_invalid_runtime_settings(monkeypatch, settings, error):
    for variable in ("FAHMM_ASR_DEVICE", "FAHMM_ASR_COMPUTE_TYPE", "FAHMM_ASR_BEAM_SIZE"):
        monkeypatch.delenv(variable, raising=False)
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match=error):
        _runtime_settings()


def test_asr_passes_opt_in_cuda_and_beam_to_whisper(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"local audio fixture")
    monkeypatch.setenv("FAHMM_ASR_DEVICE", "cuda")
    monkeypatch.setenv("FAHMM_ASR_COMPUTE_TYPE", "int8_float16")
    monkeypatch.setenv("FAHMM_ASR_BEAM_SIZE", "1")
    monkeypatch.setattr("fahmm.asr.validate_model_dir", lambda path: None)
    monkeypatch.setattr("faster_whisper.audio.decode_audio", lambda path: np.ones(16_000))
    observed = {}

    class FakeModel:
        def __init__(self, path, **kwargs):
            observed["model"] = kwargs

        def transcribe(self, audio, **kwargs):
            observed["transcribe"] = kwargs
            return iter([]), SimpleNamespace(language="vi")

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    WhisperASRBackend().transcribe(audio_path, tmp_path)
    assert observed["model"] == {
        "device": "cuda",
        "compute_type": "int8_float16",
        "local_files_only": True,
    }
    assert observed["transcribe"]["beam_size"] == 1


def test_cuda_initialization_error_is_reported_without_cpu_fallback(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"local audio fixture")
    monkeypatch.setenv("FAHMM_ASR_DEVICE", "cuda")
    monkeypatch.delenv("FAHMM_ASR_COMPUTE_TYPE", raising=False)
    monkeypatch.delenv("FAHMM_ASR_BEAM_SIZE", raising=False)
    monkeypatch.setattr("fahmm.asr.validate_model_dir", lambda path: None)
    monkeypatch.setattr("faster_whisper.audio.decode_audio", lambda path: np.ones(16_000))
    attempted = []

    class UnavailableCudaModel:
        def __init__(self, path, **kwargs):
            attempted.append(kwargs["device"])
            raise RuntimeError("CUDA runtime unavailable")

    monkeypatch.setattr("faster_whisper.WhisperModel", UnavailableCudaModel)
    with pytest.raises(RuntimeError, match="CUDA runtime unavailable"):
        WhisperASRBackend().transcribe(audio_path, tmp_path)
    assert attempted == ["cuda"]


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
    if not fixture.is_file():
        pytest.skip(
            "Provide a licensed tests/fixtures/jfk.flac for the real offline ASR smoke test"
        )
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
