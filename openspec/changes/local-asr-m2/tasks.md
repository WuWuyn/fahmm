# Tasks

## 1. Runtime and model catalog

- [x] 1.1 Add compatible faster-whisper, CTranslate2, PyAV, and Hugging Face Hub dependencies to the locked Python 3.12 environment; verify `uv sync` and an import smoke check on Windows x64.
- [x] 1.2 Build the static multilingual base/small/medium/turbo catalog with confirmed CT2 repository IDs, declared license, publisher, size, and revision policy; verify each entry against its published model files and document the source URLs and large-model resource warning.

## 2. Meeting storage and import

- [x] 2.1 Add version-2 metadata plus version-1 compatibility and restricted defaults; verify M1 recorded and unfinished fixtures still open and recover, and document the metadata migration/rollback procedure.
- [x] 2.2 Implement streaming, atomic WAV/MP3/M4A/FLAC import and audio probing; verify the four formats with local fixtures, unchanged source hashes, corrupt/unsupported-file errors, and cleanup after failed copies.
- [x] 2.3 Add a filesystem-backed meeting index, rename action, and source/status lookup; verify recorded and imported meetings appear after restart with the right state and default restricted classification.
- [x] 2.4 Add decoded local playback and timestamp seeking for recorded and imported audio; verify a segment can open at its source time in each supported format without network access.

## 3. Managed Whisper models

- [x] 3.1 Implement app-owned model manifest, strict CT2/tokenizer asset validation, and offline installed-model selection; verify a complete bundle is accepted and incomplete or incompatible bundles are rejected without fetching tokenizer assets.
- [x] 3.2 Implement user-triggered Hub downloads to staging with disk checks, progress, revision capture, asset allowlist, and retry/resume; verify an interrupted download is not listed as installed and a retry completes without meeting data in requests.
- [x] 3.3 Implement custom repository inspection and safe deletion of unused managed installations; verify incompatible repositories are rejected and deleting a model leaves meetings and active runs intact.
- [x] 3.4 Build the English Models screen and document model size, license, offline reuse, and download privacy; verify download, select, and delete controls display the expected states and errors.

## 4. Local ASR jobs and transcript files

- [x] 4.1 Implement the `ASRBackend` adapter and Windows-spawned worker using local model paths, CPU `int8`, Vietnamese default, Auto Detect, English, and timestamped segments; verify transcription with a local speech fixture while network access is blocked.
- [x] 4.2 Add the parent job controller with responsive status/progress, cancellation, retry, and bounded worker cleanup; verify the UI remains responsive during a long run and a cancelled or crashed worker leaves audio and earlier runs intact.
- [x] 4.3 Persist each completed run as immutable original segments, an editable working copy, and model/language/revision metadata with atomic writes; verify failed saves and reruns cannot overwrite prior completed results.
- [x] 4.4 Document the offline ASR boundary and run the blocked-network check for model loading, tokenizer loading, decoding, and transcription; verify no meeting-content network request occurs and no API key is required.

## 5. English application workflow

- [x] 5.1 Refactor the current window into Recorder, Meetings, Models, and Settings screens while preserving recorder controls; verify navigation and existing UI/controller tests, and document the new user flow.
- [x] 5.2 Add import, list, rename, playback, language/model selection, and Transcribe/Cancel/Retry actions to Meetings; verify one imported and one recorded meeting can be reopened and processed after restart.
- [x] 5.3 Add timestamped transcript editing, original-text inspection, active-run selection, and source playback; verify saved corrections survive restart and rerunning with a second model preserves earlier edits.

## 6. Integration acceptance

- [x] 6.1 Exercise AT-03 offline with a consented or appropriately licensed 30–60-minute Vietnamese speech file and an installed base model; verify timestamped output, responsive UI, and no API key or content egress, then record the result and sample provenance.
- [x] 6.2 Exercise AT-04 against Hugging Face with a compatible and an incompatible repository; verify progress, revision/cache reuse, selection, safe rejection, and deletion, then record the result.
- [x] 6.3 Run the full automated suite and Windows smoke flow for M1 recording/recovery plus M2 import/transcribe/review; verify no regression and update project status while leaving M1's real-meeting acceptance tasks pending.
