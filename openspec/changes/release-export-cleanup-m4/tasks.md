# Tasks

## 1. Saved-document export

- [x] 1.1 Move minutes Markdown formatting into a UI-independent service that reads an explicit saved version, adds review state and source timestamps (including a labeled appendix for edited text), and verify approved/unverified, Vietnamese, and version-selection cases in unit tests.
- [x] 1.2 Render `transcript.txt` from an explicitly selected run's saved `working.json` with readable timestamps; verify corrected text and selection of an earlier run without leaking original ASR text from a different run.
- [x] 1.3 Implement user-chosen UTF-8 file export with managed-path rejection, overwrite confirmation, same-directory atomic replacement, and no provider calls; verify cancel, existing-file preservation on failure, no partial file, and Restricted-mode socket blocking in service tests.
- [x] 1.4 Document the Markdown/TXT format, review labels, source-reference limits, and user-owned export locations in an English export guide; verify the examples against generated files.

## 2. Export controls in Meetings

- [x] 2.1 Add Export minutes and Export transcript controls for the selected saved version/run, and block unsaved editor text with an actionable message; verify selection, dirty-state, and no-data cases in Qt tests.
- [x] 2.2 Add Copy Markdown using the same saved formatter and a plain-text clipboard write only on click; verify exact clipboard content, no extra formats, and no copy when minutes edits are pending.
- [x] 2.3 Update the English user flow and README with export, clipboard/shared-location privacy, and save-before-export behavior; verify labels and documented clicks against the Meetings UI.

## 3. Meeting deletion service

- [x] 3.1 Add a per-meeting activity gate shared by recording/recovery, ASR, offline minutes, provider generation, and deletion, plus a process-lifetime Windows data-root lock that rejects a second app instance; verify direct deletion during active work, a job-start race, second-instance refusal, and crash restart without data loss.
- [x] 3.2 Implement validated single-meeting deletion using an atomic `.deleting-<id>` tombstone and no-follow/reparse-point checks; verify exact-scope removal, imported-original/export/model preservation, and rejection of path escapes in Windows tests.
- [x] 3.3 Track incomplete tombstones and safe Retry cleanup after locked-file/access errors; verify failure never reports success and retry removes only the intended meeting.
- [x] 3.4 Detect abandoned `.import-<id>` staging paths with no active owner and remove them only on explicit cleanup confirmation; verify interrupted import, live import protection, and unrelated-path preservation.

## 4. Deletion controls in Meetings

- [x] 4.1 Add a Delete meeting confirmation identifying the selected meeting and explaining removal scope, external copies, backups, and no secure-erasure promise; stop playback and refresh the list only after success, verified by Qt Confirm/Cancel tests.
- [x] 4.2 Expose active-work refusal, incomplete-deletion Retry, and orphan-import cleanup in the existing English Meetings screen; verify error/retry and four-screen navigation in Qt tests.
- [x] 4.3 Document deletion and recovery limits in the English user guide and storage guide; verify the instructions with recorded and imported test meetings.

## 5. Windows portable build

- [x] 5.1 Add a locked Windows build dependency and a frozen entry point that calls `multiprocessing.freeze_support()` before Qt imports; verify a spawned ASR worker starts and exits correctly from a development freeze build.
- [x] 5.2 Add a reproducible PyInstaller onedir build script that creates a versioned Windows x64 ZIP and SHA-256 file, checks for meeting data/secrets, and records source/dependency versions; verify the archive hash and absence of user content.
- [ ] 5.3 Inspect and exercise bundled Qt platform/multimedia, SoundCard, PyAV, CTranslate2, tokenizer, and provider dependencies in a clean Windows x64 environment with no Python/FFmpeg; verify GUI, audio import/playback, recording, and local ASR smoke.
- [ ] 5.4 Audit the exact bundled dependencies and any assets against authoritative license/attribution sources, include required notices, and block unreviewed model redistribution; verify the ZIP's notice inventory matches its contents.
- [ ] 5.5 Write English portable-install, first-model-install, offline-use, checksum, data-location, privacy, export, and deletion instructions; verify commands and paths on an extracted build without Python installed.

## 6. Integration acceptance

- [x] 6.1 Exercise AT-11 end to end with an imported and a recorded test meeting: open Vietnamese `minutes.md`/`transcript.txt` outside fahmm, confirm/cancel deletion, and verify only the chosen meeting and its temporary files are removed; record evidence without meeting content.
- [ ] 6.2 Run packaged offline/no-key Record or Import → local ASR → offline draft → export → delete and Restricted-mode egress checks on clean Windows 10 and 11 x64 targets; record exact tested environments and leave unavailable environments pending rather than passing them by inference.
- [x] 6.3 Re-run the M1–M3 automated suite, lint, and strict OpenSpec validation; publish an M4 release verification matrix for AT-01–AT-11 and Northern/Southern/mixed Vietnamese speech, keeping M1 real-meeting and any unavailable samples pending and withholding a full v1 acceptance claim.
