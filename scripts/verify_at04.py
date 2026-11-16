"""Exercise live model download, cache reuse, rejection, and deletion for AT-04."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from fahmm.models import ModelManager

COMPATIBLE = "Systran/faster-whisper-tiny"
INCOMPATIBLE = "deepdml/whisper-large-v3-turbo"  # Transformers checkpoint, not CT2.


def main() -> None:
    root = Path(os.environ["LOCALAPPDATA"]) / "fahmm" / "acceptance" / "at04-models"
    manager = ModelManager(root)
    events = []

    def progress(stage: str, current: int, total: int) -> None:
        events.append((stage, current, total))

    try:
        manager.download(INCOMPATIBLE, progress=progress)
    except ValueError as exc:
        rejection = str(exc)
    else:
        raise AssertionError("An incompatible repository was accepted")
    if manager.installed():
        raise AssertionError("The incompatible repository created an installed model")

    model = manager.download(COMPATIBLE, progress=progress)
    assert manager.select(model.id).id == model.id
    assert ModelManager(root).selected().revision == model.revision
    assert any(stage == "Downloading model files" and current > 0 for stage, current, _ in events)

    original_connect = socket.socket.connect

    def no_network(*args, **kwargs):
        raise AssertionError("Cached model reuse attempted a network connection")

    socket.socket.connect = no_network
    try:
        cached = manager.download(COMPATIBLE, progress=progress)
    finally:
        socket.socket.connect = original_connect
    assert cached.id == model.id
    assert events[-1][0] == "Already installed; using local cache"

    manager.delete(model.id)
    assert manager.installed() == []
    assert not model.path.exists()
    report = {
        "compatible_repository": COMPATIBLE,
        "incompatible_repository": INCOMPATIBLE,
        "incompatible_rejection": rejection,
        "revision": model.revision,
        "downloaded_bytes": model.bytes,
        "progress_updates": len(events),
        "cache_reused_offline": True,
        "selection_persisted": True,
        "deleted": True,
    }
    path = root.parent / "at04-result.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
