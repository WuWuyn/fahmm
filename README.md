# fahmm — Fah Meeting Minutes

*“Too tired to take notes. Too broke to pay for another subscription.”* :))))

**fahmm v1** is a free, open-source Windows app for recording meetings and producing meeting minutes. It prioritizes Vietnamese speech and minutes, requires no meeting bot, and puts privacy first. The app should remain useful without an internet connection or an API key.

## Product principles

1. **Privacy first:** Recordings and transcripts are stored and processed locally. Meeting content is never sent out automatically.
2. **Affordable:** Recording and transcription require no subscription, account, server, API key, or powerful GPU.
3. **Simple:** Record → Stop → Transcribe → Meeting Minutes. Real-time transcription and speaker diarization are outside v1.

**OpenAI-compatible does not mean local processing.** A remote endpoint receives any transcript sent to it. New meetings therefore default to **Internal/Restricted** mode, which permits an offline, source-linked minutes draft. Cloud summarization is available only when the user marks a meeting as shareable and confirms each send. A small local LLM or an approved internal AI service may be added as an optional path to higher-quality private summaries.

The current flow is **Record/Import → Stop → Transcribe locally → Review transcript → Draft minutes → Review → Export**. Whisper performs speech-to-text; an offline draft without an LLM is extractive, not a full semantic summary.

## v1 scope

- Windows 10/11 x64 with an English interface; Vietnamese remains the primary transcription language and the default language for minutes.
- Simultaneous system audio (WASAPI loopback) and microphone recording, with Record, Pause/Resume, Stop, and crash recovery.
- Audio import, local Whisper transcription with timestamps, and transcript editing.
- A Hugging Face manager for models compatible with faster-whisper.
- Offline minutes drafts or optional OpenAI-compatible summarization for meetings approved for cloud processing.
- Local per-meeting storage, Markdown/TXT export, and no remote service or account required.

Meeting bots, real-time transcription, speaker diarization, cloud sync, mobile apps, and automatic distribution of minutes are outside v1.

## Roadmap

| Milestone | Deliverable | Acceptance |
| --- | --- | --- |
| M1 — Recorder | Windows UI, system audio + mic recording, pause/stop, recovery | AT-01, AT-02, AT-10 |
| M2 — Local ASR | Audio import, Whisper, model manager, transcript editor | AT-03, AT-04 |
| M3 — Minutes & Privacy | Offline drafts, optional provider, data-egress controls | AT-05–AT-09 |
| M4 — Release | Export, cleanup, packaging, end-to-end checks | AT-11 |

The [v1 product requirements and acceptance criteria](docs/requirements-v1.md) are the source of truth. They contain 14 sections, 39 functional requirements, 8 privacy rules, and 11 acceptance tests. The [M1 recorder](openspec/changes/windows-recorder-m1/), [M2 local ASR](openspec/changes/local-asr-m2/), [M3 minutes and privacy](openspec/changes/minutes-privacy-m3/), and [M4 export and release](openspec/changes/release-export-cleanup-m4/) OpenSpec changes contain the corresponding designs, behavior specs, and task checklists.

## Run the Windows app

The desktop interface uses React, TypeScript, Vite, Tailwind CSS v4, and shadcn/ui in Tauri. It defaults to a graphite theme with blue accents and offers a light theme. The existing Python processing core runs as a bundled sidecar.

On Windows 10/11 x64, install [uv](https://docs.astral.sh/uv/getting-started/installation/), Node.js, Rust, and the Visual Studio C++ build tools. From the repository root:

```powershell
uv sync
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cd desktop
npm ci
npm run tauri dev
```

`uv sync` installs Python 3.12 if needed. Tauri starts that local Python environment as a sidecar in development; no meeting-data server or listening port is created. For recording, select the speaker output and microphone, then press **Record**. Use **Ctrl+R** to record, **Space** to pause/resume, and **Ctrl+S** to stop when focus is outside a control. After an unexpected shutdown, reopen the app and use **Recover recordings → Recover**. If the backend stops, use **Restart backend**; it inspects saved state instead of replaying the prior action.

For local transcription, open **Models** and explicitly download a compatible model, such as multilingual Base. In **Meetings**, import a WAV, MP3, M4A, or FLAC file, or select a completed recording. Choose the installed model and language (Vietnamese by default), then press **Transcribe**. You can play the audio, review timestamped segments, edit and save the transcript, and return to an earlier ASR run. Once a model is installed, transcription works without an internet connection or API key. Model downloads require an explicit click and network access; meeting audio and transcripts are not uploaded.

In **Meetings**, use **Offline draft** after reviewing the transcript. The source-linked extractive draft works without internet or an API key. You can inspect citations, play source audio, edit the offline template and minutes, approve a version, and regenerate without overwriting an approved version. For optional provider minutes, configure a profile in **Settings**, change that meeting to **Cloud Allowed**, select and review transcript rows, and confirm the destination and exact payload for each send. Provider use may cost money; Restricted meetings cannot send meeting content. See the [desktop user flow](docs/user-flow.md), [offline draft guide](docs/offline-minutes.md), and [minutes privacy design](docs/privacy-minutes.md).

After saving edits, choose a transcript run and click **Export TXT**; choose a minutes version and click **Export MD** or **Copy Markdown**. Files contain the selected saved version and readable source timestamps. Export destinations must be outside fahmm-managed data. A shared or cloud-synced folder and the system clipboard may expose meeting text to other applications. See the [export guide](docs/export.md) for format and review labels.

Meeting data is stored under `%LOCALAPPDATA%\fahmm\meetings\<id>`. Imports preserve the original source file; new meetings default to Internal/Restricted. In **Meetings**, **Delete meeting…** removes the selected app-owned meeting after confirmation. **Storage cleanup** offers retry for an incomplete deletion and separate confirmation for an abandoned import. Original imported files, exports, clipboard copies, and backups remain. See the [user flow](docs/user-flow.md) and [storage guide](docs/storage-migration.md).

To roll back, close Tauri first, check the SHA-256 file beside `release/fahmm-0.1.0-windows-x64.zip`, extract that earlier Qt candidate, and run its `fahmm.exe`. It reads the same `%LOCALAPPDATA%\fahmm` meeting library; keep a backup before testing a rollback on personal data. Never run both UIs at once because they share one instance lock.

The earlier Qt portable candidate remains under the ignored `release/` directory for rollback. To build the Tauri sidecar, run `uv run --locked python scripts/build_sidecar.py` from the repository root, then `npm run tauri build` from `desktop/`. The generated sidecar is included as a Tauri external binary. **Do not publicly distribute the candidate while bundled native dependency licenses and clean-machine checks remain open.**

## Development and current status

OpenSpec 2.0 is configured for Codex in `.agents/skills/`, with project context in `openspec/config.yaml`:

```powershell
openspec list
openspec status --change windows-recorder-m1
openspec status --change local-asr-m2
openspec status --change minutes-privacy-m3
openspec status --change release-export-cleanup-m4
openspec status --change tauri-desktop-python-sidecar
openspec validate tauri-desktop-python-sidecar --strict
openspec validate release-export-cleanup-m4 --strict
openspec validate minutes-privacy-m3 --strict
openspec validate local-asr-m2 --strict
openspec validate windows-recorder-m1 --strict
uv run --locked --extra legacy-qt pytest
uv run --locked ruff check .
cd desktop
npm test
npm run build
```

The Tauri desktop migration has four working areas and a packaged Python sidecar. The former Qt screens live in `src/legacy/qt/` for regression and rollback checks and require the optional `legacy-qt` dependency. The full Python suite passed 125 tests with one Windows privilege skip; frontend and Rust suites passed 16 and 9 tests. See [Tauri migration verification](docs/tauri-verification.md) and the [desktop architecture](docs/desktop-architecture.md). M1 remains **10/12 tasks complete**: a permitted 20-minute Teams/Meet test with both sources audible, real-hardware Pause/Resume, and interrupted-recording recovery remain open. M2 local ASR and M3 minutes/privacy are implemented; their controlled acceptance checks passed on Windows. M4 remains **18/22 tasks complete**: export and deletion work, and the earlier portable candidate passed local smoke. Clean Windows 10/11 checks and native dependency license review remain. See [project status and next steps](docs/project-status.md).

The controlled M3 privacy checks do not replace real-meeting and release acceptance. Application code is licensed under [MIT](LICENSE); dependency and model licenses must be reviewed before release.
