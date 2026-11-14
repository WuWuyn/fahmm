# Design

## Context

See [proposal.md](proposal.md) for the motivation and the five capability specs for behavior. M1 is a Python 3.12/PySide6 desktop app: `SessionController` records through an `AudioCapture` adapter, and `MeetingStore` writes version-1 JSON metadata plus chunked WAV sources and a stereo `recording.wav` under `%LOCALAPPDATA%/fahmm/meetings/<id>`. The current UI has only a Recorder screen. Two real-hardware M1 acceptance tasks remain pending and do not block designing M2. M2 must run on Windows 10/11 x64 with an ordinary CPU and 8 GB test machine, and it must keep all meeting content on the device.

## Goals / Non-Goals

**Goals:**

- Keep recording, imported audio, model assets, and transcription as separate components behind small adapters so a failed ASR job cannot damage the meeting.
- Support 30–60-minute recordings without holding the UI thread or requiring a system FFmpeg installation, API key, network, or GPU at transcription time.
- Make every network boundary auditable: the model manager may download weights only on a deliberate action; the ASR path accepts only an installed local directory.
- Preserve M1 recordings and original ASR output while extending meeting metadata and adding editable run results.

**Non-Goals:**

- No summarization, provider profiles, cloud-content approval, realtime transcript, speaker attribution, or export in this milestone.
- No automatic model download, arbitrary Hugging Face architecture conversion, or model-supplied executable code.
- No claim that a particular accent or mixed-language sample will be transcribed perfectly; quality is assessed with consented recordings.

## Decisions

1. **Extend file-based storage with versioned metadata.** Add a meeting service around `MeetingStore`; keep one folder per meeting and atomic JSON writes. Version 2 metadata adds `name`, `source_kind` (`recorded`/`imported`), relative audio path, privacy classification (`restricted`), and processing status. Read version 1 as restricted with a derived name and `recording.wav`; migrate a meeting atomically only when it is opened or updated. Preserve M1 chunk paths and recovery behavior. An imported file is streamed into a private temporary path, decoded/probed, then committed under a fixed internal filename with its original extension; the source is never edited. A directory scan remains the meeting index. **Alternative:** SQLite would add a second source of truth before search/history complexity warrants it.

2. **Use the same decoder family for import, playback, and ASR.** Add `faster-whisper` for CTranslate2 recognition and PyAV for local WAV/MP3/M4A/FLAC probing and decoding. PyAV ships FFmpeg libraries in its wheel, avoiding a separate `ffmpeg.exe`. Stream playback through Qt audio output from decoded frames so format support and source timestamp seeking do not depend on an OS media codec. Probe that a file contains usable audio before marking import complete. **Alternative:** converting each import into another full WAV simplifies playback but can duplicate hundreds of megabytes for a long meeting. [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper/blob/master/README.md?plain=1), [decoder source](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/audio.py).

3. **Treat model installation as a separate, explicit network operation.** Ship a static curated catalog of compatible multilingual CT2 Whisper repositories and metadata for base, small, medium, and a compatible large-v3-turbo variant; recheck model licenses and compatibility before locking catalog entries. Download with `huggingface_hub.snapshot_download` into an app-owned staging directory, pin the resolved commit, allowlist model assets, check disk headroom, and install only after validation. Keep an app-owned manifest with repo ID, publisher, declared license, bytes, commit, and path. Custom IDs use the same inspection and validation after the user starts a download. Retry may reuse staging files. Delete only a managed installation that is not selected by an active run. **Alternative:** loading directly by repository ID could trigger hidden downloads during transcription and makes deletion and offline guarantees harder. [Hub download API](https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download), [base model files](https://huggingface.co/Systran/faster-whisper-base/tree/main).

4. **Enforce local-only model loading.** Validate the complete CT2 model bundle, including `model.bin`, `config.json`, `tokenizer.json`, and compatible vocabulary/config assets, before selection. Pass the installed directory to `WhisperModel`, set `local_files_only=True`, and use CPU `int8` as the baseline; store the exact revision in each run. `tokenizer.json` is mandatory because a missing local tokenizer can cause faster-whisper to call a tokenizer repository even when the model is otherwise local. No transcription code receives a repo ID or network client. Model downloads never receive a meeting ID, path, or content. **Alternative:** trusting `local_files_only` alone leaves the tokenizer fallback unguarded. [WhisperModel implementation](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py).

5. **Run recognition in an isolated spawned worker process.** Define an `ASRBackend` contract and a job controller that sends only local audio/model paths and language options to one Windows `spawn` process per run. The worker decodes/transcribes, emits bounded status and segment messages, and writes no meeting files directly. The parent records progress from processed segment timestamps and commits output after successful completion. Progress is indeterminate while loading/decoding or before a reliable duration is available. Cancel signals the worker, waits briefly, then ends the isolated process if native inference does not yield; a crash leaves prior transcript runs intact. UI updates arrive on the Qt event loop. **Alternative:** a UI-thread call freezes the window; forcibly terminating a QThread running native code is unsafe. [Qt thread guidance](https://doc.qt.io/qtforpython-6.11/PySide6/QtCore/QThread.html).

6. **Store immutable recognition and editable review separately.** Each successful job gets a new `transcripts/<run-id>/` with `original.json`, `working.json`, and a run manifest. Segment IDs, start/end seconds, model/revision, selected/detected language, and creation time stay in the manifest/results. The UI saves edits to `working.json` atomically; `original.json` is never changed. A rerun creates another run and changes the active-run pointer only after success. Cancel/error creates a status record but cannot replace the active completed run. **Alternative:** one mutable transcript file would lose corrections and make reruns unreviewable. This layout also supplies source timestamps to M3 minutes.

7. **Grow the existing window into four English screens.** Keep the Recorder widget and controller boundary, and add Meetings, Models, and Settings to a stacked main window. Meetings handles import, list, rename, playback, ASR actions, and segment review. Models handles the catalog and explicit download lifecycle. Settings in M2 shows local storage/model locations and privacy information; provider configuration waits for M3. Use an application service to coordinate store, model manager, jobs, and UI rather than coupling widgets to network or ASR libraries. **Alternative:** replacing the recorder screen outright would needlessly risk M1 capture and recovery controls.

## Risks / Trade-offs

- [A model advertised as Whisper is not a usable CT2 bundle] → Validate exact local assets and loadability before offering it; keep failed downloads out of the installed list.
- [Large models are slow or exhaust RAM on an 8 GB CPU machine] → Default to multilingual base with CPU `int8`, warn for medium/turbo, and test the baseline on the minimum machine.
- [Cancellation occurs inside a long native inference call] → Keep ASR in its own process, apply a bounded graceful wait, then stop that process; never replace a completed run with partial output.
- [Disk fills during import, download, or transcript save] → Check available space where predictable, stream/copy in bounded chunks, write temporary files, and commit atomically.
- [M1 metadata migration breaks recovery] → Preserve version-1 reads, migrate lazily, and run all M1 automated storage/controller tests after the M2 changes.
- [Model cache deletion affects another installation] → Use app-owned installations and delete only validated paths inside the model root after checking active use.
- [A 30–60-minute transcript may have errors across accents or English terms] → Keep timestamps and editing, then evaluate Northern, Southern, and mixed-language samples approved for testing. A real meeting is unnecessary for the M2 functional tests.

## Migration Plan

1. Add compatibility reads for version-1 meeting metadata before writing version-2 fields; verify unfinished M1 recordings still recover.
2. Add app-owned model and transcript directories without touching existing recording chunks or `recording.wav`.
3. Upgrade a meeting only when M2 metadata is saved, using a temporary file and atomic replacement. If upgrade fails, leave the version-1 metadata and audio usable.
4. On rollback to M1, original WAV/chunk files remain ordinary local files. M1 cannot read upgraded metadata, so keep a pre-migration metadata copy until M2 has passed migration verification; document restoring it for rollback. No user meeting data is deleted as part of migration.
