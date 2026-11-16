"""Desktop sidecar entry point; future frozen builds enter here as well."""

import sys
from multiprocessing import freeze_support


def main() -> int:
    freeze_support()
    if "--worker-smoke" in sys.argv:
        return _worker_smoke()
    from fahmm.bridge.server import serve

    try:
        return serve()
    except Exception as exc:
        sys.stderr.write(f"Bridge startup failed: {type(exc).__name__}\n")
        return 1


def _worker_smoke() -> int:
    """Prove a frozen binary can spawn the actual ASR target without a model."""
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
        result = output.get(timeout=30)
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        return (
            0
            if (
                process.exitcode == 0
                and result.get("type") == "error"
                and "audio is missing" in result.get("message", "")
            )
            else 1
        )
    except queue.Empty:
        process.terminate()
        process.join(timeout=5)
        return 1
    finally:
        output.close()


if __name__ == "__main__":
    raise SystemExit(main())
