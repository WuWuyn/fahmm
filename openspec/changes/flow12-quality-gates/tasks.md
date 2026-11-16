# Tasks — review, verification and architectural follow-up

Check a task only when the named evidence exists for the **current target commit**. Reported historical test results do not pre-check any task.

## 0. Adopt the quality-gate policy (G0)

- [x] 0.1 Review requirements-v1.md FR-01–39 and AT-01–11 against the existing M1/M2/M3/Tauri specs; create a traceability map of requirement → code → test → manual acceptance. Evidence: reviewed mapping, commit SHA and reviewer.
- [x] 0.2 Re-run full Python tests and lint on the target Windows commit; record command, exact pass/skip counts, logs and environment. Evidence: a completed gate-evidence record, not a copied status report.
- [x] 0.3 Re-run frontend tests/build and Rust tests with the same protocol version; record test output and build checks. Evidence: passing artifacts and protocol fixture results.
- [x] 0.4 Verify malformed/stale/oversized IPC requests, unauthorized operations, sidecar loss, restart and no mutating auto-replay. Evidence: negative tests at frontend, Rust and Python boundaries.
- [x] 0.5 Record release/PR checklist ownership, mandatory gate criteria, exception policy and reviewer sign-off rules. Evidence: reviewed gate records stored outside any sensitive user-data directory.

## 1. Finish real-device Flow 1 recording acceptance (G1)

- [ ] 1.1 AT-01: record a permitted 20-minute Teams/Meet session using selected WASAPI loopback and microphone. Record hardware/app versions; listen to both channels for intelligible remote and local speech, not merely nonzero PCM values. Evidence: privacy-safe test notes and technical metadata.
- [ ] 1.2 AT-02: exercise Record → Pause → Resume → Stop; confirm UI state, timer, output duration and exclusion of paused content on real devices. Evidence: observations and a reproducible timestamp/duration comparison.
- [ ] 1.3 AT-10: after a committed chunk, force-close the app, reopen, recover that meeting and verify a different saved meeting is intact. Evidence: recovery report and integrity checks.
- [ ] 1.4 Test source missing/unplugged/routed to wrong output during setup; confirm clear error and no misleading “recording both” state. Evidence: device/failure matrix.
- [ ] 1.5 If system channel is too quiet, diagnose output routing, SoundCard/WASAPI loopback choice and volume before marking G1 pass; decide whether FR-07 per-source preflight/gain becomes a scoped bug fix. Evidence: before/after listen results.

## 2. Validate Flow 1 import/ASR/transcript/playback (G2)

- [ ] 2.1 Verify WAV, MP3, M4A and FLAC import plus unsupported-file and native-dialog Cancel behavior, including no existing data loss.
- [ ] 2.2 Reproduce AT-03: process 30 minutes of licensed Vietnamese audio locally with downloaded model, internet blocked, no API key, timestamp coverage and responsive Cancel/Retry. Preserve license/model revision/hash in evidence.
- [ ] 2.3 Reproduce AT-04: opt-in compatible model download, offline cache reuse, selection persistence, incompatible repository rejection and safe deletion.
- [ ] 2.4 Edit one transcript segment; reopen and confirm working text persists while original ASR output stays intact. Re-run ASR and confirm an earlier run is still selectable.
- [ ] 2.5 Click source timestamps in transcript and minutes UI; verify playback seek accuracy and scoped media access on a representative long file and after app restart.
- [ ] 2.6 Collect permitted Northern/Southern and Vietnamese-English mixed-language samples; report benchmark procedure and error examples. Agree numerical criteria separately before making accuracy claims.
- [x] 2.7 Implement selected-meeting ASR from a user-selected start time (00:00 default) through EOF; preserve absolute source timestamps and start-time provenance, reject out-of-range positions and verify retry/contract/UI behavior without claiming semantic accuracy from one clip.

## 3. Re-verify Flow 2 minutes and privacy (G3)

- [ ] 3.1 AT-05: in Restricted mode, produce an offline source-linked **extractive** minutes draft from reviewed transcript with network blocked; verify zero content egress and no provider key dependency.
- [ ] 3.2 AT-09: use transcript with missing owner, due date or decision; verify “Chưa rõ”, source references, timestamp seek and no unsupported invented assertions.
- [ ] 3.3 Edit, approve, regenerate, reopen and export minutes; verify the previous approved version remains unchanged, current edit persists, source IDs resolve, edited versions disclose parent/original origin, and any action items remain labeled as suggestions regardless of structured action-list contents.
- [ ] 3.4 AT-06–08: direct-bridge Restricted cloud request rejected; Cloud permitted preview displays destination and exact selected reviewed text; Cancel makes zero sends; Confirm makes only one authorized send.
- [ ] 3.5 Change a segment/profile/privacy state after preview or replay an expired/used confirmation; verify request denial and fresh review required. On timeout/provider error, ensure local original and approved versions survive.
- [ ] 3.6 Verify provider credentials never enter webview reads, export, diagnostics or logs; attest privacy scope for any new provider operation.

## 4. Decide and separately scope complete action management (G4)

- [ ] 4.1 Product owner signs scope decision: “action suggestions in minutes” (current v1) versus “independent tracked tasks” (new Flow 2 feature).
- [ ] 4.2 If full task management is chosen, create a separate OpenSpec change for task entities, status, owner, due date, source refs, retention/export and migration; review before implementation.
- [ ] 4.3 Add task store/service, bridge DTOs, React views and atomic/migration/approval tests; extraction creates candidates rather than silently assigning work.
- [ ] 4.4 Test edit/status updates, missing owner/deadline, deleted/changed source, optimistic concurrency, restart persistence and privacy. Accept G4 only after end-user review.

## 5. Protect architecture as features expand

- [ ] 5.1 For every bridge change, revise desktop/protocol/contract.json and matching frontend/Rust/Python validation and fixtures. Reject unknown op, invalid field, old incompatible version and dangerous unmanaged file paths.
- [ ] 5.2 Test a slow or stalled provider operation while requesting health/recording snapshot; measure whether the Rust backend-state Mutex causes unacceptable serialization. If it does, design a bounded async job/multiplexing change and test cancellation.
- [ ] 5.3 Require a persistence/migration/rollback test for any new data entity; approved minutes, transcript original and older meeting data must survive.
- [ ] 5.4 Require a privacy/threat-model review before search indexing, plugin, integration, shared workspace or remote sync can access meeting content.

## 6. End-to-end and release decisions (G5/G6)

- [ ] 6.1 Reproduce an authorized, representative real meeting → save → offline ASR → edit → source-linked minutes → approve → export and/or tracked action, with the final product scope stated precisely.
- [ ] 6.2 Attach a distinct evidence record for each gate; review failed/blocked cases and confirm no outdated evidence was used to mark a new commit accepted.
- [ ] 6.3 Complete M4 packaging/redistribution checks and run offline/privacy smoke on clean Windows 10 and 11 x64 without a separately installed Python.
- [ ] 6.4 Product owner and engineering reviewer sign off the accepted scope. Do not mark G5 complete when it promises independent tasks but G4 is not implemented; do not call G6 complete while M4 remains open.
