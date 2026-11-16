"""Require requirement, gate, and OpenSpec mapping in pull requests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def section(body: str, heading: str) -> str:
    match = re.search(rf"(?im)^## {re.escape(heading)}\s*$", body)
    if match is None:
        return ""
    next_heading = re.search(r"(?m)^## ", body[match.end() :])
    return body[
        match.end() : match.end() + next_heading.start() if next_heading else len(body)
    ].strip()


def main(event_path: Path) -> int:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    body = event.get("pull_request", {}).get("body") or ""
    requirements = section(body, "Requirements")
    gates = section(body, "Gates")
    openspec = section(body, "OpenSpec")
    errors = []
    if requirements.startswith("List ") or not re.search(r"\b(?:FR|PR|AT)-\d{2}\b", requirements):
        errors.append("Requirements must list at least one FR/PR/AT ID.")
    if gates.startswith("List ") or not re.search(r"\bG[0-6]\b", gates):
        errors.append("Gates must list at least one G0–G6 ID.")
    if not openspec or openspec.startswith("Link "):
        errors.append("OpenSpec must name the linked change or explain why none applies.")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
