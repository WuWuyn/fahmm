# Proposal

## Why

The recorder can save meetings locally, but users still cannot turn a recording or imported file into a reviewable transcript. M2 delivers the next useful offline step without requiring a meeting bot, account, API key, server, or GPU; the remaining M1 tests that need a real meeting stay pending.

## What Changes

- Import WAV, MP3, M4A, and FLAC into a new local meeting while preserving existing recorded meetings.
- Transcribe saved audio with a locally installed multilingual Whisper model, defaulting to Vietnamese and providing timestamps, progress, cancellation, and retry.
- Add an explicit Hugging Face model download flow with a curated compatible list, safe custom repository validation, offline cache reuse, selection, and deletion.
- Add a meeting list and transcript review screen where users can edit text while retaining the original ASR output and reopen or rerun a meeting.
- Add English navigation for Recorder, Meetings, Models, and Settings; keep meeting content local throughout M2.

## Capabilities

### New Capabilities

- `audio-import`: Bring supported local audio into a meeting without changing the source file.
- `local-transcription`: Run offline, post-recording speech recognition with segment timestamps and a responsive UI.
- `whisper-model-management`: Download, validate, select, reuse, and remove compatible local Whisper models.
- `transcript-review`: Persist, reopen, edit, and rerun transcripts without losing the original ASR output.
- `meeting-library`: List and reopen recorded or imported meetings and expose their processing state.

### Modified Capabilities

None. No main specs exist yet, and M1's in-flight recording requirements remain unchanged.

## Impact

M2 extends the PySide6 UI and per-meeting JSON/file storage, adds an ASR worker and model manager, and introduces faster-whisper/CTranslate2 plus Hugging Face Hub dependencies. Model downloads are user initiated and must never include meeting content. M2 does not add summarization, provider calls, realtime transcription, speaker diarization, or release packaging.
