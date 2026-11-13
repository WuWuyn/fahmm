# Design

## Context

The source specification at docs/requirements-v1.md targets Windows 10/11 x64, local files, no mandatory account/server/API key, and M1 acceptance through AT-01, AT-02, and AT-10. The UI is now English, while Vietnamese remains the primary language for future speech recognition and minutes. See the proposal and two delta specs for required behavior.

## Goals / Non-Goals

**Goals:**

- Deliver a standalone M1 desktop build with clear UI, audio adapter, controller, and storage boundaries for reuse in M2/M3.
- Protect captured data when the process terminates, retain both sources, and create a playback file with both channels.
- Test state and recovery with synthetic audio sources without requiring a live meeting in automated tests.

**Non-Goals:**

- No ASR, model downloads, LLM, cloud endpoint, or minutes generation in M1.
- No installer in M1; M4 handles packaging after license review and acceptance.

## Decisions

1. **Python 3.12, PySide6, and uv.** Python aligns with future faster-whisper and OpenAI SDK integration. PySide6 provides a Windows GUI without a browser/server. uv locks dependencies and manages development Python. Electron plus a Python worker or WPF plus Python would add another runtime and IPC in M1.
2. **SoundCard behind an AudioCapture adapter.** On Windows, SoundCard uses WASAPI and can list speaker loopbacks and microphones. Each source has its own capture thread. The adapter can be replaced if hardware acceptance reveals a problem. Do not collapse capture into a single mixed stream.
3. **Chunked PCM WAV and JSON metadata.** Each meeting has a directory under %LOCALAPPDATA%/fahmm/meetings/<id> containing versioned metadata.json, short WAV chunks per source, and recording.wav after finalization. Write each chunk to a temporary name, flush/fsync, then rename atomically; replace metadata atomically. Recovery scans committed chunks even when metadata is stale.
4. **Explicit session state.** The state machine is idle → starting → recording ↔ paused → finalizing → completed/error. The UI sends commands through a controller and never reads audio on its own thread. Do not report successful two-source recording if either device cannot open. Preserve completed chunks and offer recovery after an in-session failure.
5. **Mix on Stop/Recover.** Convert each source to mono PCM16 at 48 kHz and write stereo playback: left is system, right is microphone. Missing-source regions are silence; paused time contributes no captured content. Keep the source chunks after mixing.

## Risks / Trade-offs

- [Timing and alignment between two WASAPI streams depend on hardware] → Store per-chunk timeline offsets, listen in AT-01, and replace the adapter if drift is material.
- [SoundCard documents Windows mono and block-size quirks] → Validate returned data, retain source files, and do not claim AT-01 before real-hardware listening.
- [Power loss before the current chunk is flushed] → Use short chunks and periodic flush; only completed chunks are recoverable.
- [A device disconnects or rejects the sample rate] → Stop safely with a source-specific error and retain saved chunks; do not switch devices silently.

## Migration Plan

There was no previous meeting data to migrate. M1 writes user data outside the repository; future versions must read versioned metadata and avoid deleting unknown directories. Rolling back the app leaves ordinary WAV/JSON files readable.
