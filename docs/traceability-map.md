# Traceability: requirement → code → evidence → gate

This is a **review map at commit c44d55d82b49da9c88efdfe4b1f889e7777e7c4b**, not a test execution report. Paths are relative to the repository root. Update the map whenever source ownership or requirements change.

| Requirements / acceptance | Implementation owner | Existing tests or report | Fresh verification needed | Gate |
| --- | --- | --- | --- | --- |
| FR-01–04, FR-06; AT-01/02/10 | src/fahmm/audio.py, controller.py, storage.py; desktop/src/features/recorder/Recorder.tsx | docs/m1-verification.md; controller/storage fake-adapter suite | Permitted 20-min hardware capture with **audible** system+mic; real pause gap; kill/recover; no other meeting loss | G1 |
| FR-05 | src/fahmm/media.py; meeting import bridge and native Rust dialog | M2/Tauri service and UI regression docs | Four formats, bad input, native Cancel, no unintended recording or file grants | G2 |
| FR-08–12; AT-03 | src/fahmm/asr.py, asr_jobs.py, asr_worker.py, transcripts.py; desktop meetings/transcript UI | tests/test_at03.py; docs/m2-verification.md | Exact Windows commit, blocked-network 30-min run, timestamps, progress, Cancel/Retry, working/original edit/reopen, audio timestamp seek | G2 |
| FR-13 (P1) | ASR/transcript enhancement; not part of accepted v1 core | No P0 pass claimed | Dictionary/SRT requirements only if scheduled as separately scoped change | Future |
| FR-14–19; AT-04 | src/fahmm/models.py; Models screen/bridge | scripts/verify_at04.py; docs/m2-verification.md | Explicit download, revision/license, offline cache, incompatibility rejection, safe deletion, resource warnings | G2 |
| FR-20–26; AT-05, AT-09 | src/fahmm/offline_minutes.py, minutes_store.py; minutes UI | tests/test_at05.py, test_at09.py; docs/m3-verification.md | Source links, unknown fields, unverified draft, preserved approval, no local semantic-AI mislabeling | G3 |
| FR-27–33; AT-06/07/08 | src/fahmm/cloud_minutes.py, providers.py, provider_transport.py; bridge and minutes UI | tests/test_at06_08.py; docs/m3-verification.md | Restricted direct-bridge block; payload preview and Cancel; one-time authorization; stale/replay rejection; secret-safe failure | G3 |
| FR-34–38; AT-11 | src/fahmm/storage.py, library.py, export/deletion services; native Rust dialogs; Meetings UI | M4/Tauri verification documents | Reopen/export/confirm deletion; old data integrity; clean packaged Windows test | G0/G6 |
| FR-39 (P1) | Future export, search and language capabilities | No current v1 P0 promise | Scope/approve separately before enabling UI claims | Future |
| Independent tracked action items | No current dedicated task entity; actions are a minutes-version section | Not applicable | New OpenSpec change with stable IDs, owner/date/status, review/source versions, deletion and migration | G4 |
| End-to-end real meeting | All domains above | Historical controlled tests are not equivalent | Real devices + reviewed transcript + approved minutes; tracked task required only when advertised | G5 |
| Windows release | Tauri package/sidecar and distribution | docs/project-status.md and docs/tauri-verification.md | Clean Win10/11, redistribution/license check, installer, model/offline/privacy | G6 |

## Review sequence for a new PR

1. Mark changed files and impacted FR/AT rows; if a new capability has no row, create one.
2. Link the relevant OpenSpec requirement and scenario before implementing behavior.
3. Test the smallest changed service, then bridge contract, then frontend/Rust integration.
4. Run Restricted-mode and data-preservation negative tests if any data/provider path changed.
5. Re-run real hardware acceptance if capture, audio timing, storage or recovery changed.
6. Attach an evidence record for the new commit; reviewer determines each affected gate's state.

Do not accept a PR based solely on “125 tests passed” from a different commit. Those numbers in docs/tauri-verification.md refer to the 14 November migration verification snapshot.
