import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(name, path):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_pr_traceability_requires_real_ids_and_gate_mapping(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "## Requirements\nFR-20, AT-09\n\n## Gates\nG0, G3\n\n"
                        "## OpenSpec\nopenspec/changes/flow12-quality-gates\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    assert run_script("check_pr_traceability.py", event).returncode == 0
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": (
                        "## Requirements\nList affected FR-xx\n\n## Gates\nList affected G0–G6\n\n"
                        "## OpenSpec\nLink openspec/changes/<change-name>\n"
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    assert run_script("check_pr_traceability.py", event).returncode == 1


def test_skip_report_lists_each_case_without_claiming_acceptance(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    case = ET.SubElement(suite, "testcase", classname="tests.test_at03", name="test_offline_asr")
    ET.SubElement(case, "skipped", message="licensed sample unavailable")
    path = tmp_path / "junit.xml"
    ET.ElementTree(root).write(path, encoding="utf-8")
    result = run_script("report_pytest_skips.py", path)
    assert result.returncode == 0
    output = result.stdout
    assert "tests.test_at03.test_offline_asr" in output
    assert "Skipped tests are not acceptance evidence." in output
