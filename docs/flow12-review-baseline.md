# Flow 1–2 architecture and acceptance review

Review date: 15 November 2026 (Asia/Bangkok).
Code baseline: WuWuyn/fahmm @ c44d55d82b49da9c88efdfe4b1f889e7777e7c4b.
Project status baseline: docs/project-status.md, dated 14 November 2026.

## Confidence labels

- **Observed in source** — verified by reviewing the repository file at the pinned commit.
- **Reported pass** — the repository's verification documents report a successful test; it was not rerun during this review.
- **Open** — missing acceptance or functionality, not a pass.
- **Proposed** — a new requirement/design decision for the next change, not current behavior.

Only P0 items and explicitly advertised features block the current v1 acceptance. P1 requirements such as FR-07, FR-13, FR-19, FR-26, FR-33 and FR-39 are tracked but do not silently become release blockers; failures that prevent a P0 acceptance (for example inaudible loopback) must still be fixed.

## Status matrix

| Gate | Scope / acceptance IDs | Current evidence | Status and remaining blocker |
| --- | --- | --- | --- |
| G0 Contract, build and security baseline | Bridge contract, TS / Rust / Python, local-first invariants | Tauri migration reports 125 Python tests passed + 1 skipped; 16 frontend tests; 9 Rust tests; source has versioned JSONL bridge | **Reported automated pass, not independently rerun.** Per-commit, per-OS checks and explicit sign-off still required. |
| G1 Record, pause, recover on real devices | FR-01–04, FR-06; AT-01, AT-02, AT-10 | Capture state machine, chunk storage, WAV, recovery code exist. A 9.59 s stereo trial has both channels nonzero. | **OPEN — release blocker:** no permitted 20-minute live dual-source audible test; real Pause/Resume and forced termination/recovery still unaccepted. System channel was much quieter. |
| G2 Import, local ASR, transcript, playback | FR-05, FR-08–19; AT-03–04 | Import, faster-whisper worker, model manager, editable original/working transcript, timestamp playback. Controlled 30-minute offline Vietnamese and model install/reuse/removal reported passed. | **Reported controlled pass.** Collect Tauri end-to-end evidence and Northern/Southern/English-mixed quality samples; quality thresholds must be agreed, not invented. |
| G3 Minutes, versions and privacy | FR-20–33; AT-05–09 | Offline extractive draft and citations; minutes versions; cloud preview/confirm and restricted-mode block. Controlled AT-05–09 reported passed. | **Reported controlled pass.** Verify on latest commit and representative content. Local semantic LLM is not implemented and must not be advertised. |
| G4 Independent action item lifecycle | New scope for complete Flow 2 | Extractive minutes stores actions inside minutes content, with owner and due date often unknown. | **NOT IMPLEMENTED:** no independent task ID, assignment/status workflow, due-date edits/reminders or provenance-preserving task management. Requires a separate feature change. |
| G5 Flow 1 → 2 whole user journey | G0–G4 and one permitted real meeting | Controlled subsystem checks exist. | **BLOCKED** by G1 and G4. If Flow 2 is explicitly scoped to an editable minutes action section (v1), G4 can be marked future scope, but that narrower claim must be visible to users. |
| G6 Clean Windows distribution | M4 and packaged privacy/offline behavior | Development-host portable/installer smoke evidence reported. | **OPEN:** clean Windows 10/11, redistribution/license review, final packaged acceptance outstanding. |

## Review of implementation (not a defect claim unless indicated)

### Flow 1 — Record → Transcript → Listen

- src/fahmm/audio.py, controller.py, storage.py: two-source recording, state transitions, local chunks and recovery. The principal **acceptance gap** is live-device audibility and actual interruption behavior, not absence of a Record button.
- src/fahmm/media.py, asr.py, asr_jobs.py, asr_worker.py, models.py: import, offline job/process, model download and cancellation/retry patterns are in place. A downloaded model must work with network blocked.
- src/fahmm/transcripts.py: each run saves original.json and working.json. This meets an immutable-original option, but is **not** a fine-grained per-edit audit history. A task-specific audit ledger is a future enhancement, not a v1 failure by itself.
- desktop/src/features/meetings/AudioPlayer.tsx and desktop/src-tauri/src/media.rs: timestamp seeking and restricted media access. Verify long-file seek, expired tickets and unrelated-meeting access at the packaged desktop boundary.
- Quality risks: unusually low loopback volume, device switches, pause gap correctness, crash recovery, regional accents and Vietnamese/English code-switching. FR-07 gain/signal check is P1, but may become urgent if G1 fails.

### Flow 2 — Minutes → AI → Action Items

- src/fahmm/offline_minutes.py: local source-linked **extractive** heuristics, not a local semantic summarization model. The UI/product copy must keep these concepts separate.
- src/fahmm/minutes_store.py: structured minutes, citations, version changes and approval. Approval and evidence retention need negative tests during regenerate/edit.
- src/fahmm/cloud_minutes.py and provider services: snapshot-based selected-segment disclosure, explicit confirmation, stale/replay checks and Restricted blocking. Test through the direct bridge to ensure the UI is not the only guard.
- Current action entries are fields within a minutes version (task, owner, due_date, verification), not independent persisted work items. Completing an action manager would require new IDs, state, ownership, dates and migration behavior.
- Missing local semantic LLM is a **known future capability**, not a regression against a v1 scope that explicitly allows deterministic offline drafts.

### Cross-cutting architecture

Observed pattern:

1. React/TypeScript UI calls typed bridge client.
2. Tauri/Rust owns native dialogs, media tickets, Python process supervision.
3. Python bridge dispatches to recording, ASR, transcript, minutes, local storage and provider policy.
4. User data stays in the managed per-meeting store; only an explicitly confirmed provider path may transmit selected content.

**Potential issue to measure:** desktop/src-tauri/src/lib.rs keeps the backend Mutex guard while a sidecar call waits (timeout up to 600 seconds). This can serialize unrelated backend requests during a slow synchronous provider call. No production freeze is claimed here; add a contention test and narrow the critical section or switch affected operations to background jobs if reproduced.

**Maintenance consideration:** src/fahmm/bridge/server.py is a large dispatch table. Split by domain only with contract/fixture protection, not as a prerequisite for the live recording test.

**Protocol consideration:** desktop/protocol/contract.json has broad nested object types. Before adding task/workspace/sync operations, define stable DTOs and runtime validation for persisted and cross-process boundaries, with compatibility fixtures in all three languages.

## Prioritized work

| Priority | Work | Done when |
| --- | --- | --- |
| P0 / immediate | Complete G1 live recording AT-01/02/10 | A permitted 20-minute meeting has independently audible system/mic tracks; pause time/audio excluded; interrupted app reopens and recovers without corrupting another meeting; evidence attached. |
| P0 / current flow | Rerun G0/G2/G3 against same commit and Windows environment | All commands, exit codes and environment recorded; no content egress in Restricted mode; previous approved minutes survive edit/regeneration. |
| P0 / product definition | Decide if “Flow 2 done” means **minutes containing action suggestions** or **separate task management** | Requirement and UI copy agree. For full task lifecycle, build G4 as a separate OpenSpec change. |
| P0 / release | Complete G6 clean Win10/11 and redistribution review | Signed-off package matrix, clean-user data path, no Python install dependency, offline/privacy acceptance. |
| P1 | Cross-accent / mixed-language benchmark, loopback level UX | Sample set, reproducible quality measures and agreed thresholds; gain/signal check if audibility fails. |
| P1 | Measure/correct backend blocking; harden contract DTOs | Multi-operation contention and cross-language contract regression tests pass. |
| Later | Flow 3 search/context, Flow 4 SDK/diarization/integrations, Flow 5 mobile/sync/team | Each has a separate approved spec with migration, security and source traceability. |

## Traceability and sources

Key source documents at pinned commit:

- docs/requirements-v1.md (FR-01–39 and AT-01–11)
- docs/project-status.md (14 November status)
- docs/m1-verification.md (hardware gap and 9.59-second WAV)
- docs/m2-verification.md (controlled AT-03, AT-04)
- docs/m3-verification.md (controlled AT-05–09)
- docs/tauri-verification.md (migration tests and known limitations)
- openspec/config.yaml and existing OpenSpec M1/M2/M3/Tauri changes

Repository view: https://github.com/WuWuyn/fahmm/tree/c44d55d82b49da9c88efdfe4b1f889e7777e7c4b

This is a static review, not evidence that these tests currently pass on another machine or a later commit.
