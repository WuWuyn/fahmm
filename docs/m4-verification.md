# M4 release verification

Status as of 14 November 2026: **release candidate, not full v1 acceptance**. Development test host: Windows 11 x64, build 26200, Python 3.12.14. This report records test outcomes without retaining meeting audio, transcript text, or provider secrets.

## AT-11 — Export and deletion

**Passed on the development Windows x64 environment.** `uv run pytest -q tests/test_at11.py` completed with one passing end-to-end test. It generated a short local WAV recording with the M1 chunk/finalize path and imported a separate test WAV. Each meeting received a saved Vietnamese transcript run and minutes version. Both `transcript.txt` and `minutes.md` were exported and reopened by a separate process using UTF-8. Canceling deletion preserved the imported meeting; confirming it removed only that meeting and its temporary file. The recorded meeting and external import original remained. Confirming deletion of the recorded meeting then removed its audio, metadata, and temporary files. Both user-owned export folders and the original imported WAV remained. No meeting content was written to this report.

The supporting service and Qt tests are `tests/test_meeting_export.py`, `tests/test_export_ui.py`, `tests/test_meeting_deletion.py`, and `tests/test_delete_ui.py`; these cover selected versions, dirty edits, active-work refusal, retry after a locked-file error, path escape rejection, and explicit orphan-import cleanup.

## v1 acceptance matrix

| Check | Status | Evidence or remaining work |
| --- | --- | --- |
| AT-01 — 20-minute Teams/Meet recording, both sources audible | Pending | No permitted real meeting has been recorded; the 9.59-second user trial does not establish audibility. See [M1 verification](m1-verification.md). |
| AT-02 — Record/Pause/Resume/Stop on hardware | Pending | Short Record/Stop trial passed; real Pause/Resume and timer/audio exclusion remain. |
| AT-03 — 30-minute Vietnamese offline transcription | Pass | Controlled 1,800-second FLEURS-derived sample, installed Base model, no API key/network. See [M2 verification](m2-verification.md). |
| AT-04 — Model install/select/delete and invalid repository | Pass | M2 compatibility/download/offline reuse checks. |
| AT-05 — Restricted record/transcribe/offline draft | Pass, controlled | M3 controlled capture and blocked-network worker; real-device and packaged checks remain separate. See [M3 verification](m3-verification.md). |
| AT-06 — Restricted cloud refusal | Pass, controlled | M3 socket spy saw no send. |
| AT-07 — Cloud-permitted disclosure and confirmed provider minutes | Pass, controlled | M3 loopback provider and Qt confirmation tests. |
| AT-08 — Provider failure and retry | Pass, controlled | M3 loopback 429, unchanged local files, confirmed retry. |
| AT-09 — Unknown fields and source timestamps | Pass, controlled | M3 offline and provider tests with invalid claims removed. |
| AT-10 — Kill during live recording and recover | Pending | Real-device interruption and cross-meeting preservation remain. |
| AT-11 — Markdown/TXT export and scoped deletion | Pass, controlled | Imported plus synthetic recorded test meetings; separate-process UTF-8 file open; Cancel/Confirm and temporary removal. |

Speech coverage: **Northern Vietnamese — pending; Southern Vietnamese — pending; mixed Vietnamese-English — pending.** The 30-minute FLEURS test is read speech and does not certify accent or meeting-noise quality. No speech sample or meeting content is included in this report.

## Portable build and acceptance gates

`uv run python scripts/build_windows.py` produced `release/fahmm-0.1.0-windows-x64.zip` (155,047,417 bytes) and a matching `.zip.sha256`; an independent `Get-FileHash -Algorithm SHA256` matched **e8f4afb970caa2c3892d075e021a4ba852e7820f01873ae8acc12d7caed8a0af**. The archive contains 706 files, 42 wheel notice files, and no model weights, audio files, meeting records, or recognized secrets. Its inventory includes Qt platform/multimedia plugins, PyAV, CTranslate2, tokenizers, SoundCard, and provider code. The build script records exact runtime versions and source state, scans contents, checks notice inventory, and reopens the ZIP.

After extraction, the executable returned 0 for GUI and spawned-ASR-worker smoke with a PATH containing only Windows system directories. On this Windows 11 development host, `--pipeline-smoke` also returned 0 using a 12-second licensed Vietnamese test clip and an already installed local Base model: import → spawned local ASR (one segment) → Restricted offline draft → TXT/Markdown export → scoped deletion. Its content-free result is `.build/pipeline-frozen.json`; no test meeting, export text, or model weight is in the archive.

Clean-machine launch and packaged offline end-to-end checks on **both Windows 10 and 11 x64** remain pending; this workstation has a development Python environment and cannot stand in for either clean target. Real-device microphone/system recording and audio playback are also unverified in the frozen package. License review remains pending for bundled Qt components and PyAV's FFmpeg/codec DLLs; see [third-party notices](third-party-notices.md). No public v1 acceptance or release claim is made.

## Regression and specification gate

`uv run pytest -q --basetemp=.build/pytest-m4-final` passed **111 tests in 338.53 seconds** with exit code 0, including the 30-minute AT-03 transcription. `uv run ruff check .` passed. Strict OpenSpec validation passed for `windows-recorder-m1`, `local-asr-m2`, `minutes-privacy-m3`, and `release-export-cleanup-m4`. The first concurrent build/test run lost AT-03's shared `.pytest-tmp` directory and did not pass; the isolated rerun above is the final regression result. This gate does not replace the pending clean-machine, native hardware, licensing, or speech-coverage checks.
