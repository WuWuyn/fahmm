import multiprocessing
import os
import queue
import socket
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fahmm.asr import (
    ASR_ERROR_MESSAGES,
    ASRRuntimeError,
    WhisperASRBackend,
    _check_cuda_libraries,
    _check_cuda_runtime,
    _cuda_error_code,
    _runtime_settings,
)
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
    monkeypatch.setattr("fahmm.asr._check_cuda_runtime", lambda compute_type: None)
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
    monkeypatch.setattr("fahmm.asr._check_cuda_runtime", lambda compute_type: None)
    monkeypatch.setattr("faster_whisper.audio.decode_audio", lambda path: np.ones(16_000))
    attempted = []

    class UnavailableCudaModel:
        def __init__(self, path, **kwargs):
            attempted.append(kwargs["device"])
            raise RuntimeError("CUDA runtime unavailable")

    monkeypatch.setattr("faster_whisper.WhisperModel", UnavailableCudaModel)
    with pytest.raises(ASRRuntimeError, match="CUDA libraries are missing") as error:
        WhisperASRBackend().transcribe(audio_path, tmp_path)
    assert error.value.code == "cuda_runtime"
    assert attempted == ["cuda"]


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("CUDA driver version is insufficient", "cuda_driver"),
        ("Library cublas64_12.dll not found at C:\\private\\file", "cuda_cublas"),
        ("Library cudnn64_9.dll not found at C:\\private\\file", "cuda_cudnn"),
        ("CUDNN_STATUS_ALLOC_FAILED", "cuda_vram"),
        ("CUDA_ERROR_OUT_OF_MEMORY", "cuda_vram"),
        ("Requested compute type is not supported", "cuda_compute"),
        ("Unrecognized error with secret C:\\private", "cuda_failed"),
    ],
)
def test_cuda_error_categories_do_not_publish_private_exception_text(message, code):
    assert _cuda_error_code(RuntimeError(message)) == code
    public = str(ASRRuntimeError(code))
    assert public == ASR_ERROR_MESSAGES[code]
    assert "private" not in public and "secret" not in public


def test_cuda_runtime_checks_device_and_supported_compute_type(monkeypatch):
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 0)
    with pytest.raises(ASRRuntimeError) as error:
        _check_cuda_runtime("int8_float16")
    assert error.value.code == "cuda_driver"

    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 1)
    monkeypatch.setattr("fahmm.asr._check_cuda_libraries", lambda: None)
    monkeypatch.setattr("ctranslate2.get_supported_compute_types", lambda device: {"float16"})
    with pytest.raises(ASRRuntimeError) as error:
        _check_cuda_runtime("int8_float16")
    assert error.value.code == "cuda_compute"

    monkeypatch.setattr("ctranslate2.get_supported_compute_types", lambda device: {"int8_float16"})
    _check_cuda_runtime("int8_float16")


@pytest.mark.parametrize(
    ("missing", "code"), [("cublas64_12.dll", "cuda_cublas"), ("cudnn64_9.dll", "cuda_cudnn")]
)
def test_missing_cuda_library_is_reported_without_path(monkeypatch, missing, code):
    def missing_library(name, **kwargs):
        if name == missing:
            raise OSError("C:\\private\\dependency.dll is missing")

    monkeypatch.setattr("ctypes.WinDLL", missing_library, raising=False)
    with pytest.raises(ASRRuntimeError) as error:
        _check_cuda_libraries()
    assert error.value.code == code
    assert "private" not in str(error.value)


def test_worker_sanitizes_cuda_and_unknown_failures():
    class FakeBackend:
        def __init__(self, error):
            self.error = error

        def transcribe(self, *args):
            raise self.error

    for error, code in (
        (ASRRuntimeError("cuda_vram"), "cuda_vram"),
        (FileNotFoundError("Saved meeting audio is missing"), "audio_missing"),
        (RuntimeError("private meeting C:\\private"), "asr_failed"),
    ):
        output = queue.Queue()
        cancel = multiprocessing.get_context("spawn").Event()
        run_asr_worker("audio", "model", "vi", output, cancel, backend=FakeBackend(error))
        item = output.get_nowait()
        assert item == {"type": "error", "code": code, "message": ASR_ERROR_MESSAGES[code]}
        assert "private" not in item["message"]


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
