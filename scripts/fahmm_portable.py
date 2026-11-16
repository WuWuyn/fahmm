"""Entry point for the portable Windows build and its spawned ASR workers."""

from multiprocessing import freeze_support
from pathlib import Path


def _worker_smoke() -> int:
    """Prove the frozen ASR target can spawn, respond, and exit without a model."""
    import multiprocessing
    import queue

    from fahmm.asr_worker import run_asr_worker

    context = multiprocessing.get_context("spawn")
    output = context.Queue(maxsize=2)
    cancel = context.Event()
    process = context.Process(
        target=run_asr_worker,
        args=("__fahmm_missing_audio__", "__fahmm_missing_model__", "vi", output, cancel),
    )
    process.start()
    try:
        result = output.get(timeout=20)
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if (
            process.exitcode == 0
            and result.get("type") == "error"
            and ("audio is missing" in result.get("message", ""))
        ):
            print("Frozen ASR worker spawn: PASS")
            return 0
        print(f"Frozen ASR worker spawn: FAIL: {result!r}, exit={process.exitcode}")
        return 1
    except queue.Empty:
        process.terminate()
        process.join(timeout=5)
        print("Frozen ASR worker spawn: FAIL: no response")
        return 1
    finally:
        output.close()


def _pipeline_smoke(sample: str, report: str) -> int:
    """Exercise native import, spawned local ASR, offline draft, export, deletion."""
    import json
    import tempfile
    import wave
    from pathlib import Path

    from fahmm.asr_jobs import ASRJobController
    from fahmm.media import import_audio
    from fahmm.meeting_deletion import MeetingDeletionService
    from fahmm.meeting_export import MeetingExportService
    from fahmm.models import ModelManager
    from fahmm.offline_minutes import OfflineMinutesService
    from fahmm.storage import MeetingStore
    from fahmm.transcripts import TranscriptStore

    result = {"sample_available": False, "model_available": False, "status": "error"}
    try:
        source = Path(sample)
        result["sample_available"] = source.is_file()
        model = ModelManager().selected()
        result["model_available"] = model is not None
        if model is None:
            raise RuntimeError("Install and select a local Whisper model first")
        with tempfile.TemporaryDirectory(prefix="fahmm-package-smoke-") as directory:
            root = Path(directory)
            clip = root / "clip.wav"
            with wave.open(str(source), "rb") as incoming:
                params = incoming.getparams()
                frames = incoming.readframes(params.framerate * 12)
            with wave.open(str(clip), "wb") as outgoing:
                outgoing.setparams(params)
                outgoing.writeframes(frames)
            store = MeetingStore(root / "meetings")
            meeting_id = import_audio(store, clip)
            jobs = ASRJobController(store, ModelManager())
            jobs.start(meeting_id, model.id, "vi")
            jobs.wait(180)
            snapshot = jobs.snapshot()
            if snapshot.state != "completed":
                raise RuntimeError(f"ASR worker finished as {snapshot.state}: {snapshot.error}")
            run = TranscriptStore(store).active_run(meeting_id)
            if not run or not run["working"]:
                raise RuntimeError("ASR produced no transcript segments")
            version = OfflineMinutesService(store).generate(meeting_id)
            exporter = MeetingExportService(store)
            exporter.export_transcript(
                meeting_id, run["manifest"]["run_id"], root / "transcript.txt"
            )
            exporter.export_minutes(meeting_id, version, root / "minutes.md")
            if not (root / "transcript.txt").is_file() or not (root / "minutes.md").is_file():
                raise RuntimeError("Exports are missing")
            if store.privacy_mode(meeting_id) != "restricted":
                raise RuntimeError("The imported meeting left Restricted mode")
            MeetingDeletionService(store).delete(meeting_id)
            if store._meeting_dir(meeting_id).exists() or not clip.is_file():
                raise RuntimeError("Deletion escaped its meeting scope")
            result.update(status="pass", segments=len(run["working"]), restricted=True)
    except Exception as exc:
        result["error"] = str(exc)
    Path(report).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "pass" else 1


def main() -> int:
    import sys

    if "--worker-smoke" in sys.argv:
        return _worker_smoke()
    if "--pipeline-smoke" in sys.argv:
        index = sys.argv.index("--pipeline-smoke")
        return _pipeline_smoke(sys.argv[index + 1], sys.argv[index + 2])
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from legacy.qt.app import main as app_main

    return app_main()


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
