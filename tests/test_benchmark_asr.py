"""Check the benchmark's documented scoring and its exact distance algorithm."""

import random
from queue import SimpleQueue
from types import SimpleNamespace

import pytest

from scripts.benchmark_asr import _run_case, edit_distance, normalize, scores


def reference_distance(left, right):
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        previous, row = row, [i]
        for j, b in enumerate(right, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
    return row[-1]


def test_bit_vector_matches_independent_dynamic_program():
    generator = random.Random(2026)
    for _ in range(500):
        left = [generator.randrange(5) for _ in range(generator.randrange(30))]
        right = [generator.randrange(5) for _ in range(generator.randrange(30))]
        assert edit_distance(left, right) == reference_distance(left, right)
    for length in (64, 65, 127, 128, 129, 200):
        left = [generator.randrange(8) for _ in range(length)]
        right = [generator.randrange(8) for _ in range(length + 13)]
        assert edit_distance(left, right) == reference_distance(left, right)


def test_normalization_and_vietnamese_english_scoring():
    assert normalize("  Tiếng VIỆT,\nAPI—2026!  ") == "tiếng việt api 2026"
    result = scores("Xin chào API", "xin chào AI")
    assert result["wer"] == pytest.approx(1 / 3)
    assert result["cer"] == pytest.approx(1 / len("xinchàoapi"))
    assert result["word_edits"] == 1
    assert result["character_edits"] == 1


def test_empty_reference_is_not_an_accuracy_measure():
    with pytest.raises(ValueError, match="reference"):
        scores("...", "hello")


def test_run_without_reference_reports_speed_not_accuracy(monkeypatch):
    from fahmm import asr

    class FakeBackend:
        def transcribe(self, *_args):
            return [SimpleNamespace(text="private words")], SimpleNamespace(
                duration=10.0, detected_language="vi"
            )

    for key in ("FAHMM_ASR_DEVICE", "FAHMM_ASR_COMPUTE_TYPE", "FAHMM_ASR_BEAM_SIZE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(asr, "WhisperASRBackend", FakeBackend)
    output = SimpleQueue()
    _run_case(output, "unused.wav", "unused-model", None, "vi", "cpu", 1)
    result = output.get_nowait()
    assert result["state"] == "completed" and result["real_time_factor"] >= 0
    assert result["wer"] is None and result["cer"] is None
    assert "private words" not in str(result)
