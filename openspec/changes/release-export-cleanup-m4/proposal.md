# Proposal

## Why

M3 can produce and review local minutes, but users cannot take the result into another app or remove a meeting through the UI. M4 completes the v1 handoff and data lifecycle, then packages a Windows build that can be used without installing Python.

## What Changes

- Export the selected saved minutes version as UTF-8 `minutes.md`, export the selected saved working transcript as UTF-8 `transcript.txt`, and copy the same Markdown to the clipboard. Preserve Vietnamese text, review state, and usable source timestamps; require the user to save pending edits before export.
- Delete one selected meeting and its owned audio, transcript, minutes, metadata, and temporary files only after explicit confirmation. Refuse deletion while that meeting has active recording, ASR, minutes generation, or provider work; never delete an imported original or a separately exported file.
- Produce a Windows x64 portable ZIP with a standalone executable, SHA-256 checksum, installation/use instructions, and dependency/model license notices. The package must work without a separately installed Python or FFmpeg and must not perform automatic model downloads or meeting-content network calls.
- Run AT-11 and a release smoke/end-to-end matrix on a clean Windows environment, including an offline/no-key path and privacy checks. Record unresolved M1 real-meeting and speech-quality acceptance as release blockers rather than claiming full v1 acceptance prematurely.

## Capabilities

### New Capabilities

- `meeting-export`: User-controlled Markdown, transcript text, and clipboard output from saved meeting versions.
- `meeting-deletion`: Confirmed removal of a meeting's app-owned data with active-work and path-safety guards.
- `windows-distribution`: A portable Windows artifact, checksum, instructions, and a verified release gate.

### Modified Capabilities

None. The project has no main OpenSpec capability specs; M1–M3 behavior remains in their change specs and the v1 requirements.

## Impact

The Meetings screen gains Export and Delete controls while keeping the four existing top-level screens. New local export/deletion services use `MeetingStore`, `TranscriptStore`, and `MinutesStore`; deletion coordinates with recording, ASR, and M3 jobs. Build tooling adds a Windows frozen-app entry point and distribution scripts, with special handling for the spawned ASR worker and Qt multimedia/native dependencies. Project documentation gains release instructions, a license inventory, and acceptance evidence. Existing meeting storage and cloud authorization rules remain in force.
