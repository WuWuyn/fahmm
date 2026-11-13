# Project status and next steps

Status as of 14 November 2026. This report separates implemented code, automated evidence, and acceptance work that still needs real hardware or a permitted meeting.

## Where the project stands

| Milestone | Current state | Evidence or gap |
| --- | --- | --- |
| M1 — Recorder | Implemented; 10 of 12 OpenSpec tasks checked | Windows PySide6 app, WASAPI loopback/mic adapter, chunked local WAV storage, Pause/Resume/Stop, recovery. Fourteen automated tests, lint, and strict OpenSpec validation pass. Full AT-01/AT-02/AT-10 acceptance remains open. |
| M2 — Local ASR | Specification only | No audio import, Whisper integration, model manager, or transcript editor yet. |
| M3 — Minutes & Privacy | Specification only | No offline minutes draft, provider settings, cloud confirmation gate, or network-egress acceptance tests yet. |
| M4 — Release | Specification only | No meeting export/deletion UI, packaged Windows build, dependency/model license review, or release smoke test yet. |

The user's short real-device trial produced a completed 9.59-second stereo WAV. Both channels had nonzero samples, but the system channel was much quieter than the microphone channel. This does not establish that remote participants would be audible. Meeting recordings are stored under %LOCALAPPDATA%/fahmm/meetings, outside this repository.

## What to add next

1. **Finish M1 acceptance:** In a meeting that may be recorded, run the 20-minute Teams/Meet test with headphones and mic. Listen to both channels, exercise Pause/Resume, and document AT-01/AT-02. Run AT-10 by terminating a real recording after a flushed chunk and recovering it. If system audio is still faint, investigate the selected loopback output, Windows output routing/volume, and SoundCard behavior before closing M1.
2. **Plan and implement M2:** Create an OpenSpec change for audio import, local faster-whisper/CTranslate2 processing, a compatible Hugging Face model manager, and a transcript editor. Keep offline operation and no-API-key use as acceptance gates.
3. **Plan and implement M3:** Add the default Internal/Restricted classification, source-linked offline minutes draft, optional OpenAI-compatible provider configuration with OS-protected keys, per-send disclosure/confirmation, and blocked-network egress tests.
4. **Finish M4 release work:** Add export and deletion, review dependency/model licenses, package a Windows installer/portable build with checksum, and run end-to-end and privacy acceptance tests before any v1 release claim.

The product requirements and acceptance tests are in [requirements-v1.md](requirements-v1.md). Detailed M1 evidence is in [m1-verification.md](m1-verification.md). The active task checklist is in [OpenSpec M1 tasks](../openspec/changes/windows-recorder-m1/tasks.md).
