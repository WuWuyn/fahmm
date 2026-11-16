# G0 Windows Python CI exit investigation — 2026-11-16

Status: **LOCAL FIX VERIFIED; GITHUB RETEST PENDING**. This record is for CI reliability, not G0 or G1 acceptance. No meeting content was used.

After [PR #5](https://github.com/WuWuyn/fahmm/pull/5) passed all six checks, the [push run on `main`](https://github.com/WuWuyn/fahmm/actions/runs/43821270077) at `cd7095f02fbb52272e4aad6eefd05086d502635f` failed its Python job. Pytest printed `130 passed, 3 skipped` with no failed test or traceback, but the process returned exit 1; the aggregate check failed. Frontend, Rust and OpenSpec passed. The three skips were the real ASR model, licensed Vietnamese AT-03 sample and AT-05 sample/model cases.

The same behavior was reproduced on the Windows 11 development host: `uv run --locked --offline --extra legacy-qt python -m pytest -q -rs` printed `129 passed, 4 skipped` and then exited `-1073740791` (`0xC0000409`). With `-X faulthandler`, the 11 PySide6/Qt test modules printed `18 passed, 1 skipped` and then `Fatal Python error: Aborted` with no Python frame. Individual module runs exited 0. This points to native Qt teardown across modules, but does not identify a particular C++ object.

The proposed harness fix retains one `QApplication` for the Windows pytest session, then closes remaining top-level widgets and processes deferred deletion before session exit. CI invokes pytest through `python -m pytest` and still fails on any nonzero exit; Ruff lint/format now run even when tests fail so their status remains visible.

| Local retest after the fix | Actual result |
| --- | --- |
| All 11 Qt test modules in one process | exit 0; 18 passed, 1 skipped |
| Full Python suite, first run | exit 0; 129 passed, 4 skipped |
| Full Python suite, second run | exit 0; 129 passed, 4 skipped |
| Exact CI-style `python -m pytest -q -rs --junitxml=...` | exit 0; 129 passed, 4 skipped |
| `ruff check .` | exit 0 |
| `ruff format --check .` | exit 0; 234 files formatted |
| `openspec validate flow12-quality-gates --strict --no-interactive` | exit 0 |

Local ignored log SHA-256 values: failed GitHub Python job `ci-main-python.log` `DC5FDCFA4FD193540509216BEE89F2764A29F3EFE4D050C40261B329B10780F6`; reproduced local crash `python-tests.log` `5A3828D2EAFCC41074AC750541044F151406380F12B40C31638EF8191DB3EF5B`; Qt crash `qt-only.log` `F81363F308239C9068A9748F704864A5AACF867098EC9298A253112FFFB5107A`; Qt fixed `qt-cleanup.log` `A03CEFED747B97025186761F422C68282778300A4E2AE4E0BDFC03572293C2E2`; full retests `full-1.log` `6065094186F93861A945969339907E3AC0BE92E5A292F3134CF9C4FE3D4C3ACB`, `full-2.log` `36FB16FFA6963E6D6580A0A2DADB2676222BE9922127ADB677581E8ECA7086CD`; exact CI-style run `exact-ci.log` `96E749F74600F021C9DDFFFB9D8129384E9D561963290106F7A59945931643D4`.

The real-model/sample skips remain unaccepted G2/G3 cases. GitHub CI and human engineering review are still required before treating this as a stable G0 baseline.
