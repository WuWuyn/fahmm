# Tasks

## 1. Desktop scaffold and process contract

- [x] 1.1 Create the `desktop/` React/TypeScript/Vite and Tauri project with locked Node and Cargo dependencies, the four-route app shell, and narrow Tauri capabilities; verify frontend build and Rust check succeed on Windows without starting a local API server.
- [x] 1.2 Define one versioned operation/DTO schema for TypeScript, Rust, and Python, including request IDs, job events, safe errors, size limits, and handshake; verify cross-language fixtures accept matching messages and reject unknown versions, operations, and oversized or malformed frames.
- [x] 1.3 Add `src/fahmm/bridge/` with a sidecar entry point that reserves stdout for protocol frames, sanitizes stderr, and initializes existing services without importing Qt; verify a subprocess handshake and a service command work from the source environment.
- [x] 1.4 Add Rust sidecar supervision, request correlation, timeout/exit handling, and explicit restart without replaying mutations; verify process tests for concurrent replies, incompatibility, unexpected exit, and pending-request failure.
- [x] 1.5 Document directory ownership, protocol versioning, developer launch commands, and the no-listening-port boundary in an English architecture guide; verify the documented source-mode launch reaches a healthy handshake.

## 2. Python service adapters and privacy boundary

- [x] 2.1 Expose device enumeration and recording start/pause/resume/stop/snapshot/recovery through named bridge operations; verify fake-capture tests preserve state transitions and recover committed chunks after an interrupted sidecar.
- [x] 2.2 Expose meeting list/detail/import, saved transcript reads/edits/version selection, and saved minutes reads/edits/approval through validated identifiers; verify direct bridge tests preserve existing files, original ASR output, and prior approved minutes.
- [x] 2.3 Expose model catalog/install/delete and ASR start/cancel/status as job operations with bounded progress; verify offline model selection, cancel/retry, and preservation of the active transcript in bridge tests.
- [x] 2.4 Expose offline draft generation and cloud preview/confirm/send using server-held snapshots and the existing content-egress service; verify Restricted requests never reach transport, Cancel sends nothing, and every retry requires new confirmation through direct bridge tests.
- [x] 2.5 Expose redacted provider profiles and saved export operations without returning keys or accepting unmanaged paths from the webview; verify secret-absence, safe error, and existing-export preservation cases in bridge tests.

## 3. Scoped desktop resources

- [x] 3.1 Add native import/export selection in the Rust host, pass chosen paths only to the Python services, and return display-safe results; verify Cancel, unsupported import, managed-path rejection, and overwrite handling without a broad webview filesystem permission.
- [x] 3.2 Add a meeting-bound, expiring media ticket and range-capable custom media protocol; verify playback reads only the selected meeting and rejects traversal, expired tickets, and other-meeting access.
- [x] 3.3 Produce bounded waveform peaks and a managed playback fallback for imported formats unsupported by the Windows webview; verify seeking and waveform rendering on a long recording without a full PCM transfer through JSON.

## 4. Four-screen interface migration

- [x] 4.1 Build dark-default and light themes, graphite/slate and teal tokens, collapsible navigation, four routes, loading/error states, and text-labeled recording/privacy indicators; verify keyboard navigation, theme persistence, and legibility in both themes.
- [x] 4.2 Port Recorder device selection, explicit capture controls, timer, state indicator, and recovery list to the bridge; verify a Windows UI test of Record → Pause → Resume → Stop and an interrupted-session recovery view.
- [x] 4.3 Port Meetings list, import, selection, audio playback, and source navigation; verify an existing M1/M2/M3 meeting opens offline and an imported recording can be played without exposing its filesystem path.
- [x] 4.4 Port ASR progress/cancel/retry and timestamped transcript editing with saved-run selection; verify a completed run retains its original result, saved corrections survive restart, and failed jobs leave prior runs intact.
- [x] 4.5 Port offline minutes, citations, edit/version/approval, privacy classification, and the cloud preview/confirm/cancel flow; verify UI tests for a Restricted offline draft, provider Cancel, a fresh confirmation on retry, and visible unverified state.
- [x] 4.6 Port Models and Settings with explicit model downloads, resource warnings, redacted provider profiles, and the selected theme; verify installed-model use while offline and that saved API keys are never rendered.
- [x] 4.7 Port saved Markdown/TXT export and Copy Markdown controls with dirty-editor handling and OS destination dialogs; verify UTF-8 Vietnamese output, Cancel, overwrite confirmation, and no output from unsaved editor text.

## 5. Windows integration and cutover

- [x] 5.1 Build a Windows Python sidecar with `multiprocessing.freeze_support()` before heavy imports, place its generated binary under Tauri's external-binary input, and verify a bundled-start smoke plus a real spawned ASR worker without a separately installed Python.
- [x] 5.2 Run desktop integration checks for the offline/no-key path, Restricted-mode socket blocking, cloud preview/Cancel/Confirm, sidecar crash/restart, and media access; record pass/fail evidence against the new specs without treating pending M1 hardware tests as passed.
- [x] 5.3 Compare the four Tauri areas with existing Qt behavior and `docs/requirements-v1.md`, then switch the supported desktop developer entry point and remove Qt-only runtime code/dependency only after parity; verify the full Python suite, frontend tests, Rust tests, and Windows launch smoke.
- [x] 5.4 Update English README and user-flow documentation for the Tauri developer entry, retained data root, sidecar recovery, and rollback to the earlier Qt build; verify each documented command and a saved meeting reopened after rollback.

## Workflow follow-up

- Reconcile the pending Qt UI and PyInstaller/Qt packaging decisions in `release-export-cleanup-m4` through a separate OpenSpec planning update before final Windows distribution work. Its completed export and activity-gate service tasks remain valid.
- M4 remains responsible for final portable archive, dependency notices, deletion, and release acceptance; M1 real-hardware acceptance remains separately pending.
