# Design

## Context

See [proposal.md](proposal.md) for motivation and the three capability specs for behavior. M3 stores each meeting in `%LOCALAPPDATA%/fahmm/meetings/<32-hex-id>` with metadata v2, an app-owned audio copy, versioned transcript runs (`original.json` and edited `working.json`), and versioned minutes (`manifest.json` and `content.json`). `MeetingsPage` already selects runs and minutes versions, and `MinutesPanel` tracks unsaved editor text. `MeetingStore` validates IDs; `SessionController`, `ASRJobController`, and minutes/provider workers may still be active. Imported originals and managed Whisper installations live outside a selected meeting folder. There is no export or meeting deletion service, no frozen build, and no main OpenSpec specs yet. M1 real-meeting/hardware checks remain pending.

## Goals / Non-Goals

**Goals:**

- Make export deterministic from saved versions, independent of Qt rendering, and safe against failed/partial writes.
- Make deletion a single-meeting operation with active-work coordination, path containment, and an honest retry path.
- Produce an inspectable Windows x64 portable build and evidence for AT-11 and packaged offline/privacy behavior.

**Non-Goals:**

- SRT, DOCX, PDF, search, extra UI languages, or a local semantic LLM (v1 P1/future work, not M4's P0 release gate).
- Cloud backup, secure erasure, deleting user-created exports or OS backups, automatic updates, or an installer/code-signing service.
- Calling M1's permitted real-meeting checks complete without a suitable meeting; M4 may remain a release candidate until they pass.

## Decisions

### 1. A pure export service owns document formatting

Add `MeetingExportService` around `MeetingStore`, `TranscriptStore`, and `MinutesStore`. It takes explicit meeting, minutes-version, and transcript-run IDs, re-reads their saved data, and returns deterministic UTF-8 text. Extract the existing `render_minutes` logic from `MinutesPanel` into a reusable formatter so UI preview and file/clipboard output cannot drift. Prefix Markdown with a clear approved/unverified state and render source timestamps. For edited `user_text`, append retained source references under a heading that says they are references from the underlying draft, not proof that every edited sentence is supported. Transcript text uses the selected run's `working.json` segments and stable `HH:MM:SS` timestamps; it never uses `original.json` when working edits exist.

The UI blocks output when its minutes or transcript editor is dirty, opens a Save dialog with `minutes.md` or `transcript.txt`, and explicitly confirms replacement of an existing file. It rejects destinations inside fahmm-managed meeting/model directories so exports are separate user-owned copies. A service-level write uses a temporary file in the destination directory, flush/fsync, then `os.replace`; failure removes the temporary file and preserves an existing target. The same formatter supplies Copy Markdown through Qt's plain-text clipboard only on click. A visible note explains that shared folders and the OS clipboard may be accessible outside fahmm. No export path invokes the provider service or writes to a cloud account itself.

Alternative: exporting the editor's current text directly is shorter but can include unsaved changes without a review state, omit citations, and diverge from the saved version. Writing the target in place can truncate a prior export on disk-full or access errors.

### 2. A per-meeting activity gate precedes deletion

Extend the meeting service with an operation lease for any writer that can affect a meeting: recording/recovery, ASR, offline minutes, and provider generation; the import stage has its own lease until publication. A deletion request acquires an exclusive gate, checks these leases and the current controller/job states, then marks the meeting unavailable to new work before releasing the gate. Integrate M3's in-flight cloud-send guard with this gate so a provider request cannot race deletion. Stop selected audio playback before removing files. The service rechecks the meeting ID and metadata before acting; a UI-disabled button alone is not the protection boundary. At application startup, hold an OS-backed file lock under `%LOCALAPPDATA%/fahmm` for the process lifetime. A second fahmm instance using that data root reports that it is already open and exits before opening the store; an OS-released lock permits restart after a crash. This cross-process guard and the in-process per-meeting lease must both be exercised in tests.

After validation, atomically rename the selected directory within the meetings root to a `.deleting-<id>` tombstone. New operations resolve only the canonical 32-hex directory and therefore cannot reopen it. Scan the tree with no-follow semantics and reject reparse points/junctions before traversal; do not use a path generated from the meeting name. Remove only that tombstone and an exact associated `.import-<id>` stage. If removal fails, keep the tombstone and show an incomplete-deletion item with Retry cleanup; never report success early. A separate explicit cleanup control lists stale `.import-<id>` stages after restart only when no active import owns them. It does not sweep unknown names or model directories. The confirmation identifies the meeting and explains exports, clipboard, backups, and ordinary deletion limits.

Alternative: calling `shutil.rmtree` directly from the UI on the selected path is simple but races active writers, can leave a half-visible meeting, and gives no safe place to resume cleanup. Secure overwrite is not reliable on SSDs or backed-up volumes and is outside the stated deletion promise.

### 3. Build a pinned PyInstaller onedir portable archive on Windows

Add PyInstaller to a dedicated build dependency group and lock it with `uv.lock`. A Windows-only build script freezes a small entry point in `onedir` mode, assembles a versioned ZIP, and writes its SHA-256. The entry point calls `multiprocessing.freeze_support()` before importing Qt or other heavy app modules; PyInstaller documents this requirement for spawned workers, which M2 uses for ASR. Inspect the archive for bundled Qt platform/multimedia plugins, SoundCard, PyAV, CTranslate2, tokenizers, and other native dependencies. Run the frozen executable's smoke path and a real local ASR job; an import-only smoke is insufficient to prove the worker can spawn. [PyInstaller multiprocessing guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html), [PyInstaller onedir/windowed options](https://pyinstaller.org/en/stable/man/pyinstaller.html).

Keep model weights out of the default archive. This avoids a hidden, large, unreviewed model redistribution and preserves M2's explicit model-install action. The app can record/import before a model is installed; a preinstalled compatible model supports the complete offline path. The archive includes instructions for installing a model while online before disconnecting. All user data stays in `%LOCALAPPDATA%/fahmm`, and the build process scans the archive for accidental meeting content/secrets before packaging. Use a clean Windows build environment, pin dependency versions, record build command, OS/architecture, artifact hash, and included component versions.

Alternative: a single-file executable extracts large native libraries at each launch and is harder to inspect/debug; an installer adds privileged installation and rollback behavior beyond M4's requirement. Qt's deployment guidance also offers `pyside6-deploy`, but its Nuitka toolchain is a larger build change for this Python project. The onedir choice is provisional only in the sense that native dependency smoke tests can reveal a packaging problem; the required artifact remains a portable archive.

### 4. Treat license and acceptance evidence as release inputs

Generate a dependency inventory from the locked build environment and inspect authoritative license notices for bundled Python wheels, native libraries, and any included assets. Record each version, source, license evidence, redistribution obligations, and resulting notice file. Do not assume that the app's MIT license covers its dependencies or downloaded models. A model is not bundled unless its terms are independently reviewed. The ZIP contains required notices and user instructions.

Run service and Qt tests for export, clipboard, confirmation/cancel, active-work races, incomplete deletion, path safety, and orphan stages. AT-11 must verify Markdown/TXT with Vietnamese characters open outside the app and that confirmed deletion removes only the chosen meeting and its associated temporary files. Then test the frozen app on clean Windows 10 and 11 x64 with no Python/FFmpeg: launch, record/import, explicit model install, disconnect network, local ASR, offline minutes, export, delete, restart, and Restricted-mode socket checks. Re-run the M1–M3 suite and privacy gates. Record Northern, Southern, and mixed Vietnamese-English speech cases only with approved samples; leave unavailable cases pending. The release report has pass/fail/pending entries and cannot claim full v1 acceptance while M1 real-hardware checks are pending.

Alternative: a source-tree smoke and green unit tests would miss frozen-worker imports, missing Qt plugins, packaging leaks, and clean-machine dependencies.

## Risks / Trade-offs

- [Edited minutes text no longer maps exactly to citations] → Preserve the underlying draft references in a clearly labeled appendix; never portray them as automatic semantic verification.
- [A selected export destination is a shared drive or cloud-synced folder] → Require a deliberate Save/Copy action and disclose that these destinations are outside fahmm's local processing boundary.
- [A writer starts during deletion] → Use a shared operation gate plus a tombstone before removal, with a process-lifetime data-root lock and race tests.
- [A junction, locked file, or access error prevents removal] → Reject traversal, keep a retryable tombstone, and report incomplete deletion without touching outside targets.
- [Frozen ASR/native media dependencies fail on a clean PC] → Test worker spawn and multimedia paths on clean Windows 10/11 x64 before shipping; keep build logs and a diagnosable release candidate.
- [A bundled dependency or model has unmet redistribution terms] → Audit exact locked artifacts before distribution and include notices; block publication if obligations are unresolved.
- [No suitable permitted real meeting exists] → Keep AT-01/AT-02/AT-10 pending and describe the artifact as a candidate, not an accepted v1 release.

## Migration Plan

M4 does not change meeting metadata or transcript/minutes schemas. Existing M1–M3 meetings remain readable and gain export/delete controls without migration. Packaging changes only how the Python app starts; `%LOCALAPPDATA%/fahmm` remains the data root across source and portable runs. For rollback, close the portable app and run the previous source build or archive against the same local data; exports are ordinary user-owned files, and no automatic deletion occurs. Incomplete `.deleting-<id>` tombstones remain local for an explicit retry or manual backup, not silently discarded.
