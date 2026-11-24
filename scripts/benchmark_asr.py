"""Compare local ASR configurations without saving audio or transcript content.

Each configuration runs in a separate process, sequentially, with a wall-time
and low-available-memory limit. Output is a new JSONL file containing hashes,
resource observations, and WER/CER, not the source or recognized words.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
import platform
import shutil
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

import psutil

if __package__:
    from .benchmark_memory import MIB, MemoryGuard, MemoryPolicy, MemoryWatchdog
else:
    from benchmark_memory import MIB, MemoryGuard, MemoryPolicy, MemoryWatchdog


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(text: str) -> str:
    """NFKC/casefold, replace punctuation and symbols with spaces, collapse whitespace.

    WER uses these whitespace-separated units: for Vietnamese they are generally
    syllables rather than linguistically segmented words. CER removes spaces.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(
        "".join(" " if unicodedata.category(char)[0] in "PSZC" else char for char in text).split()
    )


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    """Exact Levenshtein distance with a bit-vector, for long transcripts."""
    if len(left) > len(right):
        left, right = right, left
    size = len(left)
    if not size:
        return len(right)
    masks: dict[str, int] = {}
    for index, item in enumerate(left):
        masks[item] = masks.get(item, 0) | (1 << index)
    mask = (1 << size) - 1
    top = 1 << (size - 1)
    positive, negative = mask, 0
    score = size
    for item in right:
        equal = masks.get(item, 0)
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        add = negative | ~(horizontal | positive)
        remove = positive & horizontal
        score += bool(add & top) - bool(remove & top)
        add = ((add << 1) | 1) & mask
        remove = (remove << 1) & mask
        positive = (remove | ~(vertical | add)) & mask
        negative = add & vertical
    return score


def scores(reference: str, hypothesis: str) -> dict:
    reference, hypothesis = normalize(reference), normalize(hypothesis)
    ref_words, hyp_words = reference.split(), hypothesis.split()
    ref_chars, hyp_chars = reference.replace(" ", ""), hypothesis.replace(" ", "")
    if not ref_words or not ref_chars:
        raise ValueError("The reference must contain words after normalization")
    word_edits = edit_distance(ref_words, hyp_words)
    char_edits = edit_distance(ref_chars, hyp_chars)
    return {
        "wer": word_edits / len(ref_words),
        "cer": char_edits / len(ref_chars),
        "reference_units": len(ref_words),
        "hypothesis_units": len(hyp_words),
        "word_edits": word_edits,
        "reference_characters": len(ref_chars),
        "character_edits": char_edits,
    }


def _run_case(
    output, audio: str, model: str, reference: str | None, language: str, device: str, beam: int
):
    # Environment changes apply only to this child; the user's app is unaffected.
    os.environ["FAHMM_ASR_DEVICE"] = device
    os.environ["FAHMM_ASR_COMPUTE_TYPE"] = "int8" if device == "cpu" else "int8_float16"
    os.environ["FAHMM_ASR_BEAM_SIZE"] = str(beam)
    try:
        from fahmm.asr import WhisperASRBackend

        start = time.monotonic()
        segments, info = WhisperASRBackend().transcribe(Path(audio), Path(model), language)
        parts = [segment.text for segment in segments]
        inference_seconds = time.monotonic() - start
        metrics = (
            scores(Path(reference).read_text(encoding="utf-8-sig"), " ".join(parts))
            if reference is not None
            else {"wer": None, "cer": None, "accuracy_note": "not measured: no reference"}
        )
        output.put(
            {
                "state": "completed",
                "inference_seconds": inference_seconds,
                "audio_seconds": info.duration,
                "real_time_factor": inference_seconds / info.duration,
                "detected_language": info.detected_language,
                "segments": len(parts),
                **metrics,
            }
        )
    except Exception as exc:
        # Exceptions can contain user paths or recognized text. Do not write them to the report.
        result = {"state": "failed", "error_type": type(exc).__name__}
        from fahmm.asr import ASR_ERROR_MESSAGES, ASRRuntimeError

        if isinstance(exc, ASRRuntimeError) and exc.code in ASR_ERROR_MESSAGES:
            result.update(error_code=exc.code, error=ASR_ERROR_MESSAGES[exc.code])
        output.put(result)


def _gpu_total_mib() -> int | None:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return sum(int(line.strip()) for line in result.stdout.splitlines() if line.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _available_memory() -> int | None:
    try:
        return psutil.virtual_memory().available
    except (OSError, psutil.Error):
        return None


def _run_gated(gate, *args) -> None:
    # The worker may not start model loading before the RAM watchdog is active.
    if gate.wait(15):
        _run_case(*args)


def run_case(
    audio: Path,
    model: Path,
    reference: Path | None,
    language: str,
    device: str,
    beam: int,
    *,
    max_seconds: float,
    min_free_mib: int,
    grace_seconds: float,
    gpu_metrics: bool,
    min_start_free_mib: int = 5120,
    emergency_free_mib: int = 1536,
    sample_seconds: float = 0.2,
) -> dict:
    policy = MemoryPolicy(
        min_start_free_mib, min_free_mib, emergency_free_mib, grace_seconds, sample_seconds
    )
    available = _available_memory()
    preflight_reason = MemoryGuard(policy).preflight(available)
    if preflight_reason:
        return {
            "state": "stopped",
            "reason": preflight_reason,
            "wall_seconds": 0,
            "minimum_system_available_mib": round(available / MIB, 1)
            if available is not None
            else None,
        }
    context = multiprocessing.get_context("spawn")
    output = context.Queue(maxsize=1)
    gate = context.Event()
    process = context.Process(
        target=_run_gated,
        args=(
            gate,
            output,
            str(audio),
            str(model),
            str(reference) if reference is not None else None,
            language,
            device,
            beam,
        ),
    )
    start = time.monotonic()
    peak_rss = 0
    observed_cpu_seconds = 0.0
    peak_gpu: list[int] = []
    gpu_stop = threading.Event()
    gpu_thread = None
    last_report = start
    reason = None
    response = None
    watchdog = None
    result_ready = threading.Event()
    result_box = []

    def stop_owned_worker(_reason: str) -> None:
        try:
            if process.is_alive():
                process.terminate()
        except (OSError, ValueError):
            return

    def read_result() -> None:
        try:
            result_box.append(output.get())
        except (EOFError, OSError, ValueError):
            pass
        finally:
            result_ready.set()

    def sample_gpu() -> None:
        while not gpu_stop.is_set():
            gpu = _gpu_total_mib()
            if gpu is not None:
                peak_gpu.append(gpu)
            if gpu_stop.wait(5):
                return

    try:
        process.start()
        observed = psutil.Process(process.pid)
        watchdog = MemoryWatchdog(
            policy, _available_memory, stop_owned_worker, initial_available=available
        )
        watchdog.start()
        if watchdog.reason is None:
            gate.set()
        reader = threading.Thread(target=read_result, daemon=True)
        reader.start()
        if gpu_metrics:
            gpu_thread = threading.Thread(target=sample_gpu, daemon=True)
            gpu_thread.start()
        while True:
            now = time.monotonic()
            if watchdog.reason:
                reason = watchdog.reason
                break
            if result_ready.is_set():
                response = (
                    result_box[0]
                    if result_box
                    else {"state": "failed", "error_type": "WorkerOutputUnavailable"}
                )
                break
            if not process.is_alive():
                result_ready.wait(timeout=1)
                response = (
                    result_box[0]
                    if result_box
                    else {"state": "failed", "error_type": "WorkerExited"}
                )
                break
            try:
                peak_rss = max(peak_rss, observed.memory_info().rss)
                cpu = observed.cpu_times()
                observed_cpu_seconds = max(observed_cpu_seconds, cpu.user + cpu.system)
            except psutil.Error:
                pass
            if now - last_report >= 60:
                observed_available = watchdog.minimum_available
                print(
                    f"  {now - start:.0f}s elapsed; minimum sampled available RAM "
                    f"{observed_available / MIB:.0f} MiB"
                    if observed_available is not None
                    else "RAM sample unavailable",
                    flush=True,
                )
                last_report = now
            if now - start >= max_seconds:
                reason = "wall_time_limit"
                break
            result_ready.wait(timeout=policy.sample_seconds)
    finally:
        try:
            if response is not None and reason is None:
                process.join(timeout=0.2)
            if process.pid is not None:
                if process.is_alive():
                    with contextlib.suppress(OSError, ValueError):
                        process.terminate()
                    process.join(timeout=5)
                if process.is_alive():
                    with contextlib.suppress(OSError, ValueError):
                        process.kill()
                process.join(timeout=5)
        finally:
            if watchdog is not None:
                watchdog.stop()
            gpu_stop.set()
            if gpu_thread is not None:
                gpu_thread.join(timeout=4)
            output.cancel_join_thread()
            output.close()
    if watchdog is not None and watchdog.reason:
        reason = watchdog.reason
    if reason:
        response = {"state": "stopped", "reason": reason}
    minimum = watchdog.minimum_available if watchdog is not None else available
    return {
        **response,
        "wall_seconds": round(time.monotonic() - start, 3),
        "peak_process_rss_mib": round(peak_rss / 1024**2, 1),
        "sampled_process_cpu_seconds": round(observed_cpu_seconds, 3),
        "minimum_system_available_mib": round(minimum / MIB, 1) if minimum is not None else None,
        "peak_total_gpu_memory_mib": max(peak_gpu) if peak_gpu else None,
    }


def _model_arg(value: str) -> tuple[str, Path]:
    label, separator, directory = value.partition("=")
    if not separator or not label.strip() or not directory.strip():
        raise argparse.ArgumentTypeError("Use LABEL=PATH for each model")
    model = Path(directory).resolve()
    if not (model / "model.bin").is_file():
        raise argparse.ArgumentTypeError("A model directory with model.bin is required")
    return label.strip(), model


def _revision_arg(value: str) -> tuple[str, str]:
    label, separator, revision = value.partition("=")
    if not separator or not label.strip() or not revision.strip():
        raise argparse.ArgumentTypeError("Use LABEL=REVISION for a model revision")
    return label.strip(), revision.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path, help="Authorized UTF-8 reference transcript")
    parser.add_argument("--model", type=_model_arg, action="append", required=True)
    parser.add_argument("--revision", type=_revision_arg, action="append", default=[])
    parser.add_argument("--corpus-label", default="unspecified")
    parser.add_argument("--corpus-license", default="unspecified")
    parser.add_argument("--beam", type=int, choices=range(1, 11), action="append")
    parser.add_argument("--language", choices=("vi", "en", "auto"), default="auto")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--output", type=Path, required=True, help="New JSONL report, never overwritten"
    )
    parser.add_argument("--max-seconds", type=float, default=3600)
    parser.add_argument("--min-start-free-mib", type=int, default=5120)
    parser.add_argument("--min-free-mib", type=int, default=2048)
    parser.add_argument("--emergency-free-mib", type=int, default=1536)
    parser.add_argument("--grace-seconds", type=float, default=5)
    parser.add_argument("--gpu-metrics", action="store_true", help="Sample whole-GPU usage")
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or args.max_seconds <= 0:
        parser.error("The wall-time limit must be finite and positive")
    try:
        policy = MemoryPolicy(
            args.min_start_free_mib, args.min_free_mib, args.emergency_free_mib, args.grace_seconds
        )
    except ValueError as exc:
        parser.error(str(exc))
    if not args.audio.is_file() or (args.reference is not None and not args.reference.is_file()):
        parser.error("Audio and supplied reference files must exist")
    if args.reference is not None and not normalize(args.reference.read_text(encoding="utf-8-sig")):
        parser.error("The reference transcript must not be empty")
    labels = [label for label, _ in args.model]
    if len(set(labels)) != len(labels):
        parser.error("Model labels must be unique")
    revisions = dict(args.revision)
    if len(revisions) != len(args.revision) or not set(revisions).issubset(labels):
        parser.error("Revision labels must be unique and match a supplied model")
    if not args.output.parent.is_dir():
        parser.error("The report directory must already exist")
    beams = args.beam or [1, 5]
    if len(set(beams)) != len(beams):
        parser.error("Beam sizes must be unique")
    metadata = {
        "type": "metadata",
        "audio_sha256": file_hash(args.audio),
        "reference_sha256": file_hash(args.reference) if args.reference is not None else None,
        "corpus_label": args.corpus_label,
        "corpus_license": args.corpus_license,
        "normalization": "NFKC, casefold, punctuation/symbols to spaces; WER by whitespace units; CER without spaces",
        "language": args.language,
        "device": args.device,
        "memory_guard": policy.as_dict(),
        "python_version": platform.python_version(),
        "faster_whisper_version": importlib.metadata.version("faster-whisper"),
        "ctranslate2_version": importlib.metadata.version("ctranslate2"),
        "logical_cpus": psutil.cpu_count(),
        "gpu_memory_scope": "total GPU, not attribution to this process"
        if args.gpu_metrics
        else "not sampled",
        "models": [
            {
                "label": label,
                "revision": revisions.get(label),
                "model_bin_sha256": file_hash(path / "model.bin"),
                "asset_sha256": {
                    name: file_hash(path / name)
                    for name in (
                        "config.json",
                        "tokenizer.json",
                        "vocabulary.txt",
                        "vocabulary.json",
                    )
                    if (path / name).is_file()
                },
            }
            for label, path in args.model
        ],
    }
    with args.output.open("x", encoding="utf-8") as report:

        def record(item):
            report.write(json.dumps(item, ensure_ascii=False) + "\n")
            report.flush()
            os.fsync(report.fileno())

        record(metadata)
        for label, model in args.model:
            for beam in beams:
                print(f"Running {label}, {args.device}, beam={beam}", flush=True)
                result = run_case(
                    args.audio,
                    model,
                    args.reference,
                    args.language,
                    args.device,
                    beam,
                    max_seconds=args.max_seconds,
                    min_free_mib=args.min_free_mib,
                    grace_seconds=args.grace_seconds,
                    gpu_metrics=args.gpu_metrics,
                    min_start_free_mib=args.min_start_free_mib,
                    emergency_free_mib=args.emergency_free_mib,
                )
                record({"type": "case", "model": label, "beam": beam, **result})
                print(f"  {result['state']}", flush=True)
                if result["state"] != "completed":
                    print("Stopping remaining cases after incomplete run.", flush=True)
                    raise SystemExit(2)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
