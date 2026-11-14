# Tauri migration verification

Evidence collected on Windows x64 on 14 November 2026, using disposable `%LOCALAPPDATA%` directories. This is development-host verification, not a clean-machine release acceptance or the pending M1 real-meeting hardware test.

| Behavior | Evidence | Result |
| --- | --- | --- |
| Frozen sidecar starts without invoking a separate Python and spawns the real ASR worker target | `uv run --locked python scripts/build_sidecar.py` runs `--worker-smoke` and a protocol handshake | Pass |
| Host starts the adjacent sidecar | Release `fahmm-desktop.exe` remained running with one child `fahmm-sidecar.exe` and created the instance lock under a disposable data root | Pass |
| Windows installer contains the sidecar | `npm run tauri build` completed MSI and NSIS; the MSI `File` table includes `fahmm-sidecar.exe` | Pass on development host |
| Default Python installation excludes Qt | `uv sync --locked` removed PySide6; source-mode sidecar handshake passed; `uv build --wheel` produced a wheel with bridge files and no legacy Qt modules | Pass |
| Frontend and Rust regression suites | `npm ci`, `npm test -- --run` (16 tests), `npm run build`, and `cargo test --lib` (9 tests) on the cutover tree | Pass |
| shadcn/ui and blue theme in the packaged app | Button, Card, Badge, Tabs, Dialog, form controls, and progress use shadcn/ui components with blue dark/light tokens. A release executable launched with a disposable data root showed Recorder devices, an empty Meetings library, the model catalog, and Settings from the live sidecar without a backend warning | Pass on development host |
| Full Python regression and long offline ASR | `uv run --locked --extra legacy-qt pytest -q` finished with exit code 0: 125 passed, 1 skipped. AT-03 runs its real 30-minute ASR acceptance in a separate pytest process to keep native Qt/ASR teardown outside the main suite | Pass |
| Existing meeting and offline draft without a provider key | `uv run --locked python scripts/verify_tauri_sidecar.py` seeds a local transcript, opens it through frozen JSON-lines IPC, and saves an unverified extractive version | Pass |
| Restricted mode has no content egress | `tests/test_bridge_cloud.py` replaces socket connect with a failure and rejects a Restricted preview; frozen integration records zero requests against a loopback provider | Pass |
| Provider preview, Cancel, fresh Confirm, and single use | Frozen integration sends zero requests on Cancel and exactly one on Confirm; replay is rejected. `MinutesPanel.ui.test.tsx` checks the separate UI decisions | Pass |
| Sidecar restart and durable state | Frozen integration closes and restarts the sidecar, reopens the meeting and saved version, and rejects an old process's media ticket | Pass |
| Scoped media and long waveform | `tests/test_bridge_media.py`, `tests/test_bridge_waveform.py`, Rust range tests, and `AudioPlayer.ui.test.tsx` cover meeting binding, expiry, traversal rejection, bounded ranges, FLAC fallback, 65-second peak extraction, and a mocked 65-minute seek | Pass (one symlink test skipped due Windows privilege) |
| Recording and document UI state | React tests cover Record → Pause → Resume → Stop with fake capture, recovery, old and imported meeting navigation, transcript corrections, minutes privacy, model selection, theme, and saved export controls. Recorder input levels now come from system/microphone RMS in `recording.snapshot`, verified in `tests/test_bridge_recording.py` | Pass in simulated UI; hardware capture remains pending |
| Rollback to earlier Qt candidate | `uv run --locked --extra legacy-qt python scripts/verify_qt_rollback.py` checks the prior ZIP checksum, launches its executable with a temporary data root, and selects a saved meeting in the legacy Meetings UI | Pass |

The Tauri webview receives no unrestricted filesystem capability. Native import/export dialogs are Rust commands; Python validates meeting identifiers and managed-directory exclusions. The sidecar has no listening meeting-data port. The loopback HTTP server in `verify_tauri_sidecar.py` is a disposable provider emulator used only for this test.

## Qt and v1 behavior parity

| Area | Existing Qt behavior and v1 requirement | Tauri replacement |
| --- | --- | --- |
| Recorder | System loopback and microphone selection, explicit start/pause/resume/stop, elapsed timer, crash recovery (FR-01–FR-06) | Named capture bridge operations, labeled state/timer, shortcuts, and recovery list; uses the same `SessionController` and `MeetingStore` |
| Meetings and transcript | Import, local playback, model/language selection, ASR progress and retry, timestamped working edits and original run retention (FR-08–FR-18) | Native import dialog, scoped WaveSurfer playback, selected installed model, language menu, ASR job status, saved-run editor and source navigation |
| Minutes and privacy | Extractive offline draft, template, citations, version approval, explicit provider disclosure (FR-19–FR-34; PR-01–PR-08) | Same Python minutes/privacy services through the bridge, with template editor, source links, unverified labels, per-meeting badge, selected/reviewed rows, exact payload dialog, and single-use send |
| Models, Settings, and output | Explicit model download/delete, redacted provider settings, saved Markdown/TXT export, guarded deletion and cleanup (FR-15–FR-17, FR-35–FR-38) | Model jobs and resource warnings, redacted profiles, OS save dialogs, saved-version copy/export, deletion confirmation and cleanup retries |

The Qt source remains in `src/legacy/qt/` through the optional `legacy-qt` extra for regression and rollback checks. The normal Python dependency set, wheel, and frozen Tauri sidecar exclude Qt. The earlier Qt ZIP is a rollback candidate, not the new development entry point.

Run verification from the repository root:

```powershell
uv run --locked python scripts/build_sidecar.py
uv run --locked python scripts/verify_tauri_sidecar.py
uv run --locked --extra legacy-qt python scripts/verify_qt_rollback.py
uv run --locked --extra legacy-qt pytest -q
uv run --locked ruff check .
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cd desktop
npm ci
npm test -- --run
npm run build
cd src-tauri
cargo test --lib
cargo build --release
```

M1 AT-01/AT-02/AT-10 still require a permitted Teams/Meet recording on real devices, including audible loopback, Pause/Resume, and crash recovery. The legacy Qt portable candidate also still needs M4's separate license and clean Windows review.
