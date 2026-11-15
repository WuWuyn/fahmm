# v1 release acceptance record

Status: **not accepted for public release**. Updated 15 November 2026. This record separates controlled development checks from real-device and clean-machine acceptance. It contains no meeting audio, transcript, provider payload, or secret.

## Candidate identity

| Item | Current evidence |
| --- | --- |
| Product under test | Tauri desktop with the bundled Python sidecar; the legacy Qt ZIP is a rollback candidate only |
| Source revision | `c44d55d82b49da9c88efdfe4b1f889e7777e7c4b` plus uncommitted release-test changes; a fixed, committed candidate is still required |
| Development host | Windows 11 x64, build 26200; Python and build tools are installed, so this is not a clean target |
| Internal portable candidate | `.build/release/fahmm-tauri-0.1.0-windows-x64-portable.zip`; SHA-256 `c62cc047d06e3f946b89f120d80af4dc8c3a56bcdd70ae383637ddb3a62a6b92` |
| Installer | Not produced in this rerun: WiX and NSIS downloads failed because GitHub DNS resolution was unavailable |
| Test operator and date | Record with each real-device or clean-machine run before closing its gate |

## Development-host rerun — 15 November 2026

This run used Windows 11 x64 build 26200 with development tools installed. It is **not** clean-machine or real-meeting evidence. The ZIP is an internal test candidate built from revision `c44d55d82b49da9c88efdfe4b1f889e7777e7c4b` plus uncommitted verification and packaging changes; `BUILD_INFO.json` therefore records `sourceDirty: true`. Do not distribute it as v1.

| Check | Command or method | Observed result |
| --- | --- | --- |
| Frozen Python sidecar | `uv run --locked --offline python scripts/build_sidecar.py` | Pass: Windows x64 validation, worker smoke, JSON-lines handshake and health |
| Tauri host without installer | `cd desktop; npm run tauri build -- --no-bundle` | Pass: release `fahmm-desktop.exe` built |
| MSI and NSIS | `cd desktop; npm run tauri build`; `npm run tauri build -- --bundles nsis` | Blocked at bundle stage: WiX/NSIS tool downloads from GitHub failed with DNS error `11001`; the host binary itself built |
| Portable ZIP | `uv run --locked --offline python scripts/package_tauri_portable.py --allow-dirty` | Pass: ZIP and `.sha256` produced; no model weights or meeting data copied by the packager |
| Portable extraction/start | PowerShell `Get-FileHash`, `Expand-Archive`, launch extracted host with disposable `LOCALAPPDATA` | Pass on development host: ZIP and both embedded executable hashes match, host stayed running, sidecar processes started, `.instance.lock` appeared. The two sidecar processes are consistent with the PyInstaller one-file bootloader and worker process; this is a process check, not a UI or clean-machine check |
| Frozen sidecar local operations | `uv run --locked --offline python scripts/verify_tauri_sidecar.py --offline-only` | Pass: synthetic WAV import, timestamped transcript fixture, no-key offline draft, Markdown/TXT export, scoped meeting deletion preserving source and exports, media ticket and peaks, restart and durable saved version. Actual ASR and provider/egress cases were not run |
| Full frozen provider integration | `uv run --locked --offline python scripts/verify_tauri_sidecar.py` | Blocked in the sandbox: Windows Credential Manager returns access denied (`CredReadW` error 5) when the test saves a provider profile. No provider result claimed |
| Frontend tests | Node 24.22.1, `cd desktop; npm test -- --run` | Pass: 7 files, 16 tests. System Node 22.13.0 cannot load locked `undici` 8.12.4, which requires Node 22.19 or later |
| Rust tests | `cd desktop/src-tauri; cargo test --lib` | Pass: 9 tests |
| Python bridge tests | `uv run --locked --offline pytest -q tests/test_bridge_cloud.py tests/test_bridge_media.py tests/test_bridge_recording.py` | Pass: 5 tests, 1 Windows privilege-dependent skip |
| Python full suite | `uv run --locked --offline --extra legacy-qt pytest -q` | Not run: offline cache lacks `pyside6-webengine` required by the legacy Qt extra. The default environment cannot collect 12 Qt UI modules without PySide6 |
| Changed Python scripts | `uv run --locked --offline ruff check scripts/build_sidecar.py scripts/verify_tauri_sidecar.py scripts/package_tauri_portable.py` | Pass |

The ZIP manifest records these locked versions: Tauri CLI 2.12.4, Tauri Rust 2.12.5, React 19.3.1, Vite 8.3.8, faster-whisper 1.2.1, CTranslate2 4.9.0, PyAV 18.1.0, PyInstaller 6.22.3, and SoundCard 0.4.6. Its binary SHA-256 values are in `BUILD_INFO.json`. For a release candidate, commit the source, rebuild both binaries, rerun the packager without `--allow-dirty`, and test the new hash on both clean Windows targets.

## Acceptance matrix

| Check | Evidence already available | Current status | Required release evidence |
| --- | --- | --- | --- |
| AT-01: 20-minute Teams/Meet capture | [M1 short device trial](m1-verification.md) saved a 9.59-second stereo WAV; system level was much lower than mic | Pending real meeting | Permitted 20-minute call on the fixed Tauri candidate; both sources intelligible, no bot |
| AT-02: Record/Pause/Resume/Stop | [M1 simulated controls](m1-verification.md) and short real Record/Stop | Partial | Real hardware states, timer, valid file, and no paused audio |
| AT-03: 30-minute Vietnamese offline ASR | [M2 controlled 1,800-second sample](m2-verification.md), 195 timestamped segments, socket-blocked worker | Controlled pass | Repeat packaged local-ASR path on clean Windows targets; quality cases below remain separate |
| AT-04: Model management | [M2 compatible/incompatible repository checks](m2-verification.md) | Controlled pass | Explicit first download, offline reuse, and selection in the fixed package |
| AT-05: Restricted offline flow | [M3 controlled flow](m3-verification.md) and [Tauri sidecar integration](tauri-verification.md) | Controlled pass | Packaged Record or Import → local ASR → offline draft with no account/key or content egress |
| AT-06: Restricted cloud refusal | [M3 blocked-network check](m3-verification.md) and [Tauri sidecar check](tauri-verification.md) | Controlled pass | Packaged direct refusal with zero provider requests |
| AT-07: Confirmed provider request | [M3 preview/confirm check](m3-verification.md) and [Tauri sidecar check](tauri-verification.md) | Controlled pass | Packaged preview, Cancel, fresh Confirm, and exactly one send to a controlled endpoint |
| AT-08: Provider error/retry | [M3 loopback error check](m3-verification.md) | Controlled pass | Preserve saved local work during packaged provider error and retry |
| AT-09: Unknown facts and citations | [M3 source-linked minutes checks](m3-verification.md) | Controlled pass | Review packaged Vietnamese minutes and seek cited source audio |
| AT-10: Interrupted recording recovery | [M1 synthetic crash tests](m1-verification.md) and [Tauri simulated recovery](tauri-verification.md) | Pending real device | Kill live capture after committed chunks; recover and preserve another meeting |
| AT-11: Export and scoped deletion | [M4 controlled imported/recorded cases](m4-verification.md) | Controlled pass | Packaged TXT/MD open outside app; confirm/cancel deletion affects only selected meeting |

## Vietnamese speech coverage

| Case | Current status | Required evidence |
| --- | --- | --- |
| Northern accent | Pending | Approved sample provenance, local model/revision, timestamped output, observed errors |
| Southern accent | Pending | Approved sample provenance, local model/revision, timestamped output, observed errors |
| Vietnamese with English terms | Pending | Approved sample provenance, local model/revision, timestamped output, observed errors |

The M2 FLEURS-derived 30-minute sample is concatenated read speech. It confirms an offline long-file path, not meeting-noise or accent accuracy.

## Clean-machine and distribution gates

| Gate | Windows 10 x64 | Windows 11 x64 | Evidence required |
| --- | --- | --- | --- |
| Installer or portable start without development Python/FFmpeg | Pending | Pending | Exact candidate hash, OS build, GUI and sidecar health |
| First model download, offline reuse, import/playback/timestamp | Pending | Pending | Tested model revision, supported file, source navigation |
| Restricted packaged pipeline and no-egress check | Pending | Pending | Local ASR/minutes/export/delete result and zero content sends |
| Provider preview/Cancel/Confirm in package | Pending | Pending | Controlled endpoint request count, no payload in this report |
| Exact bundled native licenses and notices | Pending | Pending | Component inventory and resolved redistribution review; see [notices](third-party-notices.md) |
| First-run and rollback instructions | Pending | Pending | Commands and paths exercised on extracted/installed candidate |

Each pending result stays pending until its named environment and candidate hash are recorded. A defect fix requires a new artifact hash and rerun of the affected checks. The v1 release claim remains blocked while any row above is pending or fails.

The still-open source change tasks are M1 `5.2` and `5.3` (real meeting and recovery), and M4 `5.3`–`5.5` and `6.2` (clean package, notices, instructions, and offline pipeline). The M4 Qt-specific package evidence does not replace the Tauri checks above.
