# Flow 1/2 traceability: requirement → code → test → acceptance

Engineering review: Codex, 15 November 2026 (Asia/Bangkok). The Flow 1/2 review started at code anchor `7c8ede3` (`fix(minutes): label extractive drafts and action suggestions`); the bilingual UI entries include the subsequent topic-branch implementation. This map covers every FR-01–39 and AT-01–11 in `docs/requirements-v1.md`. The separate `docs/flow12-review-baseline.md` preserves the historical `c44d55d` review. A code path or automated test in this table is not a manual gate acceptance.

| Requirement / acceptance | Existing OpenSpec owner | Current code | Automated evidence | Manual acceptance still needed | Gate |
| --- | --- | --- | --- | --- | --- |
| FR-01–04; AT-01/02 | `windows-recorder-m1/audio-recording`; `flow1-acceptance` | `src/fahmm/audio.py`, `controller.py`, `storage.py`; `desktop/src/features/recorder/Recorder.tsx` | `tests/test_audio.py`, `test_controller.py`, `test_bridge_recording.py`, `test_activity_gate.py` | Permitted 20-minute Teams/Meet; listen to remote and local speech; real Pause/Resume timing and source state | G1 |
| FR-05 | `local-asr-m2/audio-import`; `flow1-acceptance` | `src/fahmm/media.py`; native Rust import dialog; meetings UI | `tests/test_import.py`, `test_bridge_meetings.py`, `test_media.py` | WAV/MP3/M4A/FLAC, unsupported file and native Cancel on the packaged app | G2 |
| FR-06; AT-10 | `windows-recorder-m1/recording-recovery`; `flow1-acceptance` | `src/fahmm/storage.py`, `controller.py` | `tests/test_crash.py`, `test_storage.py`, `test_controller.py` | Kill after a committed live chunk, recover and compare another meeting | G1 |
| FR-07 (P1) | `flow1-acceptance` signal/device scenario; no accepted v1 implementation change | Selected source and level indicators in recorder; per-source gain and mid-session switching unverified | `tests/test_audio.py`, `test_bridge_recording.py` cover controlled source behavior | Diagnose low loopback volume; scope gain/preflight work if audibility blocks AT-01 | Future/G1 if blocking |
| FR-08–12; AT-03 | `local-asr-m2/local-transcription`, `transcript-review`; `flow1-acceptance` | `src/fahmm/asr.py`, `asr_jobs.py`, `asr_worker.py`, `transcripts.py`; transcript UI | `tests/test_asr.py`, `test_asr_jobs.py`, `test_at03.py`, `test_transcripts.py`, `test_bridge_jobs.py` | Licensed 30-minute Vietnamese audio, installed model, blocked network, Cancel/Retry, edit/reopen and timestamp coverage | G2 |
| FR-13 (P1) | M2 future enhancement | No accepted dictionary or SRT delivery | None claimed | Separate scope and evidence if scheduled | Future |
| FR-14–18; AT-04 | `local-asr-m2/whisper-model-management`; `flow1-acceptance` | `src/fahmm/models.py`; Models UI and bridge | `tests/test_models.py`, `test_models_page.py`; `scripts/verify_at04.py` | Opt-in download, license/revision, offline cache, incompatible repo, delete and disk failure | G2 |
| FR-19 (P1) | M2 model management | Model metadata and resource messaging | `tests/test_models.py` | Verify RAM/GPU warning and revision on target machine | Future/G2 |
| FR-20–25; AT-05/09 | `minutes-privacy-m3/meeting-minutes`, `meeting-privacy`; `flow2-acceptance` | `src/fahmm/offline_minutes.py`, `minutes_store.py`, `meeting_export.py`; `desktop/src/features/minutes/MinutesPanel.tsx`; edited-version parent/original origin | `tests/test_at05.py`, `test_at09.py`, `test_offline_minutes.py`, `test_minutes_store.py`, `test_meeting_export.py`, `desktop/src/MinutesPanel.ui.test.tsx` | Restricted offline draft, unknown fields, source seek, immutable approved version, edited provenance and action-suggestion wording | G3 |
| FR-26 (P1) | M3 future option | No local semantic LLM in v1 | None claimed | Separate local-model/internal-endpoint scope | Future |
| FR-27–32; AT-06/07/08 | `minutes-privacy-m3/provider-profiles`, `cloud-minutes`, `meeting-privacy`; `flow2-acceptance` | `src/fahmm/cloud_minutes.py`, `providers.py`, `credentials.py`, `provider_transport.py`; bridge and minutes UI | `tests/test_at06_08.py`, `test_bridge_cloud.py`, `test_cloud_minutes.py`, `test_provider_transport.py`, `test_credentials.py` | Direct Restricted bypass denial, exact preview and one send, stale/replay rejection, timeout preservation on target build | G3 |
| FR-33 (P1) | M3 cloud minutes | Prompt/token/preview controls in minutes UI | `tests/test_cloud_minutes_ui.py`, `test_bridge_cloud.py` | Review displayed payload against actual request | G3/Future |
| FR-34–38; AT-11 | `release-export-cleanup-m4/meeting-export`, `meeting-deletion`, `windows-distribution`; Tauri `desktop-workflows` | `src/fahmm/storage.py`, `library.py`, `meeting_export.py`, `meeting_deletion.py`; native dialogs and Meetings UI; bilingual React UI store | `tests/test_at11.py`, `test_meeting_export.py`, `test_meeting_deletion.py`, `test_library.py`; frontend/Rust tests and language toggle test | Reopen, external export, confirmed delete and clean packaged Windows 10/11; bilingual UI review | G0/G6 |
| FR-39 (P1) | Future export/search/language scope; separate `local-project-workspaces-search` proposal exists | English/Vietnamese toggle implemented; SRT/DOCX/PDF, cross-meeting search and further UI languages remain open | Frontend language toggle test | Implement and accept remaining items through scoped changes | Future |
| PR-01–08 | `minutes-privacy-m3/meeting-privacy`; `flow2-acceptance` | Python privacy policy, cloud confirmation, OS secret store, local export/deletion | `tests/test_at05.py`, `test_at06_08.py`, `test_bridge_cloud.py`, `test_credentials.py`, `test_meeting_export.py` | Network-blocked Restricted and packaged privacy/secret audit | G3/G6 |
| Independent managed actions | Separate `source-linked-action-items` change now exists; its tasks remain open | Minutes currently contain action suggestions, not independent task entities | Export labeling regression in `tests/test_meeting_export.py` | Product scope decision, service/bridge/UI implementation, lifecycle tests and user review | G4 |
| Whole journey / release | `v1-recording-release-acceptance`; `flow12-quality-gates` | All domains above; `.github/workflows/quality-gates.yml` | Per-commit G0 logs in `docs/evidence/` and local `.build/flow12-g0/`; CI checks and PR mapping | Authorized meeting through export; clean Windows 10 and 11; redistribution and owner sign-off | G5/G6 |

## Review rule

For each change, identify affected rows and rerun the matching service, bridge, frontend and Rust checks on the new code commit. Capture a separate gate record with environment and reviewer. Controlled fixtures cannot establish audible live recording, speech quality across accents or clean-machine packaging. The `source-linked-action-items` and `local-project-workspaces-search` changes are plans, not shipped features.

## One-click meeting minutes implementation — 18 November 2026

OpenSpec owner: `one-click-meeting-minutes`. The primary desktop action now generates a universal, unverified, source-linked draft from the active saved transcript using `meetingType=general`. The offline extractor covers chronological windows across a long recording, classifies only explicit cues, keeps empty universal sections visible, and leaves absent meeting facts unknown. Advanced specialized types and the separately authorized provider workflow remain available. See `docs/one-click-meeting-minutes.md` for the user journey.

| Check | Observed result | Boundary |
| --- | --- | --- |
| OpenSpec strict validation | `one-click-meeting-minutes` valid | Spec consistency only |
| Python focused service/store/export/bridge/provider tests | 96 passed; one-hour fixture and bridge-to-export smoke passed | Synthetic transcript, not ASR accuracy |
| Complete Python suite with loopback and Windows Credential Manager access | 215 passed, 4 skipped | Six sandbox-only failures cleared on rerun with those local OS capabilities |
| Desktop React tests | 44 passed across 9 files after the sidecar compatibility fix | Simulated bridge/UI state |
| Desktop TypeScript/Vite build; Rust `cargo check`; Rust `cargo test` | All passed; 9 Rust tests passed | Does not establish packaged Windows 10/11 release acceptance |
| Ruff on changed Python files | Passed | Static check only |

The 60-minute fixture is timestamped text, not recorded speech. A permitted real Vietnamese meeting, transcript accuracy, source-audio review, audio capture reliability, and clean-machine packaging still require the Flow 1/2 manual gates. The local one-click draft is extractive and is not a semantic AI summary; FR-26 remains future scope. No merge, push, or deployment was performed for this change.

| Feature gate | Status and evidence |
| --- | --- |
| G0 — inspection | Complete: current domain model, transcript versions, minutes store, exporter, bridge, provider boundary, desktop panel, and related OpenSpec changes were inspected. |
| G1 — OpenSpec | Complete: proposal, design, delta spec, and 7/7 tasks; strict validation passed. |
| G2 — domain/backend | Complete for the offline extractive path: universal sections, citations, chronological coverage, storage and export verified by the focused Python tests. Semantic local LLM generation is not implemented. |
| G3 — desktop UI | Complete in automated UI checks: one-click action, progress, missing transcript, retry, unsaved-edit guard, version selection, and bilingual labels. |
| G4 — automated checks | Complete: full Python, React, TypeScript/Vite, Ruff, Rust check and Rust tests passed in the noted environment. |
| G5 — integrated smoke | Bridge-to-saved-export smoke passed with a synthetic transcript including a corrected working segment. Real desktop/audio end-to-end acceptance remains unverified. |

## Desktop sidecar compatibility regression — 18 November 2026

The Tauri release executable had been rebuilt with current React code while its adjacent frozen Python sidecar was still from an older build. The older sidecar did not advertise `minutes.sourceDrift`. Minutes generation could save a version, but the desktop's version-opening request failed, and its feedback was below the long document. The local meeting library retained the generated versions; this fix does not delete or merge them.

The sidecar was rebuilt from current Python code. A frozen-sidecar smoke test with a temporary Vietnamese transcript passed generation, readback, rendered body, source-drift check, Markdown export, and active-version listing. Tauri now checks that the sidecar advertises every operation in `desktop/protocol/contract.json` before a release build. The desktop shows generation and opening failures beside the action and blocks approval when source checks are unavailable. The new release was built in a separate target directory while the prior app held its sidecar file open. Live verification in the user's still-open desktop remains pending until that app is closed and the new executable is launched.
