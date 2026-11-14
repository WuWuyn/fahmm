# Project status and next steps

Status as of 14 November 2026. This report separates implemented code, automated evidence, and acceptance work that still needs real hardware or a permitted meeting.

## Where the project stands

| Milestone | Current state | Evidence or gap |
| --- | --- | --- |
| M1 — Recorder | Implemented; 10 of 12 OpenSpec tasks checked | Windows PySide6 app, WASAPI loopback/mic adapter, chunked local WAV storage, Pause/Resume/Stop, recovery. Fourteen automated tests, lint, and strict OpenSpec validation pass. Full AT-01/AT-02/AT-10 acceptance remains open. |
| M2 — Local ASR | Implemented; 20 of 20 OpenSpec tasks checked | Audio import, local Whisper with timestamped transcript editing, and compatible Hugging Face model management. AT-03 passed on a 30-minute Vietnamese sample without network access or an API key; AT-04 passed with compatible download, offline reuse, deletion, and incompatible-repository rejection. The full suite passed 38 tests and the Windows app smoke launch passed. |
| M3 — Minutes & Privacy | Implemented; 21 of 21 OpenSpec tasks checked | Source-linked offline minutes, version review/edit/approval, optional OpenAI-compatible profiles with Windows-protected keys, and a per-send cloud disclosure gate. Controlled AT-05–AT-09 checks passed on Windows. The complete M1–M3 suite passed 84 tests; Windows app smoke, lint, and strict OpenSpec validation passed. |
| M4 — Release | 18 of 22 OpenSpec tasks checked; portable candidate built | Saved-version Markdown/TXT export, Copy Markdown, guarded deletion, retry/orphan cleanup, and controlled AT-11 pass. The 155 MB ZIP passes checksum, GUI, worker, and local ASR/offline/export/delete smoke on this development host. Native license review and clean Windows 10/11 packaged checks remain open. |
| Tauri desktop migration | 24 of 24 OpenSpec tasks checked | Recorder, Meetings with transcript/minutes, Models, and Settings use the same Python services and data root. The full Python suite passed 125 tests with one Windows privilege skip; frontend and Rust suites passed 16 and 9 tests. Installer, frozen sidecar, privacy, and Qt rollback evidence is in the Tauri verification guide. This is development-host evidence, not M1 real-hardware or M4 clean-machine release acceptance. |

The user's short real-device trial produced a completed 9.59-second stereo WAV. Both channels had nonzero samples, but the system channel was much quieter than the microphone channel. This does not establish that remote participants would be audible. Meeting recordings are stored under %LOCALAPPDATA%/fahmm/meetings, outside this repository.

## What to add next

1. **Finish M1 acceptance:** In a meeting that may be recorded, run the 20-minute Teams/Meet test with headphones and mic. Listen to both channels, exercise Pause/Resume, and document AT-01/AT-02. Run AT-10 by terminating a real recording after a flushed chunk and recovering it. If system audio is still faint, investigate the selected loopback output, Windows output routing/volume, and SoundCard behavior before closing M1.
2. **Finish M4 release work:** Validate the portable ZIP and checksum, resolve the PyAV/FFmpeg and Qt redistribution notices, and run packaged offline/privacy checks on clean Windows 10 and 11 x64 before any v1 release claim. The candidate does not bundle model weights.

The product requirements and acceptance tests are in [requirements-v1.md](requirements-v1.md). Detailed evidence is in [M1 verification](m1-verification.md), [M2 verification](m2-verification.md), [M3 verification](m3-verification.md), [M4 verification](m4-verification.md), and [Tauri migration verification](tauri-verification.md). The task checklists are in [OpenSpec M1](../openspec/changes/windows-recorder-m1/tasks.md), [OpenSpec M2](../openspec/changes/local-asr-m2/tasks.md), [OpenSpec M3](../openspec/changes/minutes-privacy-m3/tasks.md), [OpenSpec M4](../openspec/changes/release-export-cleanup-m4/tasks.md), and [OpenSpec Tauri migration](../openspec/changes/tauri-desktop-python-sidecar/tasks.md).
