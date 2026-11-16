# v1 release acceptance record

Status: **not accepted for public release**. Updated 16 November 2026. This record separates controlled development checks from real-device and clean-machine acceptance. It contains no meeting audio, transcript, provider payload, or secret.

A newer **G1-only portable test candidate** from code commit `1352c90` is documented in the [G1 preflight record](evidence/flow12-g1-preflight-2026-11-16.md). It has not undergone live recording or clean-machine tests. The installer and portable hashes below belong to the older `2211d44` release candidate; they cannot accept the newer code.

## Candidate identity

| Item | Current evidence |
| --- | --- |
| Product under test | Tauri desktop with the bundled Python sidecar; the legacy Qt ZIP is a rollback candidate only |
| Source revision | `2211d4494408bcb80897a861f256e58b42b6b698`; clean source tree at package time (`sourceDirty: false`) |
| Development host | Windows 11 x64, build 26200; Python and build tools are installed, so this is not a clean target |
| Internal portable candidate | `.build/release/fahmm-tauri-0.1.0-windows-x64-portable.zip`; SHA-256 `535faa477ea0cbf955668a6e428b8ac9ea369d3bcb3140adb0f411225791f3d3` |
| MSI installer | `desktop/src-tauri/target/release/bundle/msi/fahmm_0.1.0_x64_en-US.msi`; SHA-256 `e91c936cff9234948ee6a0cd5b784b284081cf69b3ee0be083f0a68179f4c606` |
| NSIS installer | `desktop/src-tauri/target/release/bundle/nsis/fahmm_0.1.0_x64-setup.exe`; SHA-256 `005906758ebb98843de4e3551e85d20c05889cd16c7f46d79be7f5891271869a` |
| Test operator and date | Record with each real-device or clean-machine run before closing its gate |

## Committed candidate on the development host — 15 November 2026

The sidecar and both installers were built from the clean source revision above. Tauri's full build produced MSI and NSIS after WiX and NSIS were downloaded and hash-validated outside the sandbox. The portable host was then built with `npm run tauri build -- --no-bundle` and packaged without `--allow-dirty`. All three artifacts contain the same sidecar SHA-256 `26bbc79b1e41714ac65248b4f5161751db58b0a8d7bb9f672ea2819b302ca636`.

| Check | Result and scope |
| --- | --- |
| MSI payload and start | `msiexec /a` extracted the MSI to `.build/release/msi-admin-7483e1c2` (exit 0). It contains `fahmm-desktop.exe` and `fahmm-sidecar.exe`; the sidecar hash matches the source binary. The extracted host stayed running with sidecar processes and created `.instance.lock` under a disposable `LOCALAPPDATA`. This verifies the MSI payload start, not a full installer wizard or system registration. |
| Portable integrity and start | SHA-256 of the ZIP and both extracted binaries matched `.zip.sha256` and `BUILD_INFO.json`; `sourceRevision` matched the commit and `sourceDirty` was false. The extracted host stayed running with sidecar processes and created `.instance.lock` under a separate disposable `LOCALAPPDATA`. |
| Frozen local and provider path | `verify_tauri_sidecar.py --offline-only` passed import, seeded timestamped transcript, offline minutes, export, scoped deletion, media, and restart. A full run outside the sandbox passed Restricted refusal, preview Cancel, Confirm, single-use send, and restart; the loopback provider received exactly one confirmed request. Actual ASR was not run. |
| Regressions after build | React/Vitest: 16/16; Rust: 9/9; targeted Python bridge: 5 passed, 1 Windows privilege-dependent skip; Ruff: passed. Node 24.22.1 was used for Vitest. |

Locked versions in the ZIP manifest include Tauri CLI 2.12.4, Tauri Rust 2.12.5, React 19.3.1, Vite 8.3.8, faster-whisper 1.2.1, CTranslate2 4.9.0, PyAV 18.1.0, PyInstaller 6.22.3, and SoundCard 0.4.6. Build commands and binary hashes are in `BUILD_INFO.json`. The exact sidecar archive listing is [v1-sidecar-archive.txt](v1-sidecar-archive.txt): 523 entries, including 175 `.dll`/`.pyd` files and 24 files named as license or notice material. No `model.bin` or audio file appears in that listing. The native set includes PyAV/FFmpeg DLLs and `libx264`/`libx265`; redistribution obligations and notice coverage remain unresolved.

## Initial development-host rerun — 15 November 2026

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

That dirty-tree ZIP was superseded by the committed candidate above. Its failures and environmental constraints are retained here as regression history. The current candidate still needs the same hash tested on both clean Windows targets.

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
| Exact bundled native licenses and notices | Pending | Pending | Component inventory and resolved redistribution review; see [Tauri native review](v1-native-license-review.md) |
| First-run and rollback instructions | Pending | Pending | [Tauri first-run guide](tauri-first-run.md); checksum/extraction/start checked on the development host, full workflow and paths pending clean targets |

Each pending result stays pending until its named environment and candidate hash are recorded. A defect fix requires a new artifact hash and rerun of the affected checks. The v1 release claim remains blocked while any row above is pending or fails.

The still-open source change tasks are M1 `5.2` and `5.3` (real meeting and recovery), and M4 `5.3`–`5.5` and `6.2` (clean package, notices, instructions, and offline pipeline). The M4 Qt-specific package evidence does not replace the Tauri checks above.
