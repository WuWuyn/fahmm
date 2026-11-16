"""Publish every pytest skip separately from the suite pass/fail result."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main(path: Path) -> int:
    if not path.exists():
        report = (
            "## Python skipped tests\n\nJUnit report was not produced; inspect the test step.\n"
        )
    else:
        root = ET.parse(path).getroot()
        skipped = []
        for case in root.iter("testcase"):
            reason = case.find("skipped")
            if reason is not None:
                name = f"{case.get('classname', '')}.{case.get('name', '')}"
                skipped.append((name, reason.get("message", "")))
        report = f"## Python skipped tests\n\n{len(skipped)} skipped.\n"
        for name, reason in skipped:
            report += f"\n- `{name}`: {reason.replace(chr(10), ' ')[:240]}"
        report += "\n\nSkipped tests are not acceptance evidence.\n"
    print(report)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
