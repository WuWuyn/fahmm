"""Manual Ollama acceptance smoke using fictional one-hour transcript fixtures."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
import uuid
from pathlib import Path

from fahmm.local_llm import DEFAULT_MODEL, LocalMinutesJobs
from fahmm.meeting_export import MeetingExportService
from fahmm.minutes_store import MinutesStore
from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Installed Ollama model to compare")
    parser.add_argument("--meeting-type", default="general", help="Meeting type to generate")
    args = parser.parse_args()
    fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "one_click_minutes_hour.json").read_text(encoding="utf-8")
    )
    with tempfile.TemporaryDirectory(prefix="local-minutes-", dir=ROOT / ".build") as directory:
        root = Path(directory)
        meetings = MeetingStore(root / "meetings")
        meeting_id = meetings.create({})
        run_id = uuid.uuid4().hex
        model = InstalledModel(uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 1, root)
        TranscriptStore(meetings).save_run(
            meeting_id, run_id, model, "vi", {"duration": 3600}, fixture
        )
        jobs = LocalMinutesJobs(meetings, root / "llm.json")
        jobs.select(args.model)
        availability = jobs.availability()
        if not availability["ready"]:
            raise SystemExit(f"Ollama model is not ready: {availability}")
        print(
            f"Local model: {availability['selectedModel']}; fixture: {len(fixture)} segments",
            flush=True,
        )
        started = time.monotonic()
        jobs.start_generation(meeting_id, args.meeting_type)
        last_progress = -1
        while True:
            status = jobs.status("_generation")
            progress = round(status["progress"] * 100)
            if progress != last_progress:
                print(f"Progress: {progress}%", flush=True)
                last_progress = progress
            if status["state"] != "running":
                break
            time.sleep(1)
        if status["state"] != "completed":
            raise SystemExit(f"Local AI minutes failed: {status['error']}")
        markdown = MeetingExportService(meetings).minutes_markdown(meeting_id, status["versionId"])
        suffix = re.sub(r"[^a-z0-9-]", "-", args.model.casefold())
        target = ROOT / ".build" / f"local-minutes-smoke-{suffix}-{args.meeting_type}.md"
        target.write_text(markdown, encoding="utf-8")
        (ROOT / ".build" / f"local-minutes-smoke-{suffix}-{args.meeting_type}.json").write_text(
            json.dumps(
                MinutesStore(meetings).read_version(meeting_id, status["versionId"]),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Saved {target} in {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
