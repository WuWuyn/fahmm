# fahmm — Fah Meeting Minutes

*“Too tired to take notes. Too broke to pay for another subscription.”* :))))

**fahmm v1** is a free, open-source Windows app for recording meetings and producing meeting minutes. It prioritizes Vietnamese speech and minutes, requires no meeting bot, and puts privacy first. The app should remain useful without an internet connection or an API key.

## Product principles

1. **Privacy first:** Recordings and transcripts are stored and processed locally. Meeting content is never sent out automatically.
2. **Affordable:** Recording and transcription require no subscription, account, server, API key, or powerful GPU.
3. **Simple:** Record → Stop → Transcribe → Meeting Minutes. Real-time transcription and speaker diarization are outside v1.

**OpenAI-compatible does not mean local processing.** A remote endpoint receives any transcript sent to it. New meetings therefore default to **Internal/Restricted** mode, which permits an offline, source-linked minutes draft. Cloud summarization is available only when the user marks a meeting as shareable and confirms each send. A small local LLM or an approved internal AI service may be added as an optional path to higher-quality private summaries.

The planned flow is **Record/Import → Stop → Transcribe locally → Review transcript → Draft minutes → Review and export**. Whisper performs speech-to-text; an offline draft without an LLM is extractive, not a full semantic summary.

## v1 scope

- Windows 10/11 x64 with an English interface; Vietnamese remains the primary transcription language and the default language for minutes.
- Simultaneous system audio (WASAPI loopback) and microphone recording, with Record, Pause/Resume, Stop, and crash recovery.
- Audio import, local Whisper transcription with timestamps, and transcript editing.
- A Hugging Face manager for models compatible with faster-whisper.
- Offline minutes drafts or optional OpenAI-compatible summarization for meetings approved for cloud processing.
- Local per-meeting storage, Markdown/TXT export, and no required backend or account.

Meeting bots, real-time transcription, speaker diarization, cloud sync, mobile apps, and automatic distribution of minutes are outside v1.

## Roadmap

| Milestone | Deliverable | Acceptance |
| --- | --- | --- |
| M1 — Recorder | Windows UI, system audio + mic recording, pause/stop, recovery | AT-01, AT-02, AT-10 |
| M2 — Local ASR | Audio import, Whisper, model manager, transcript editor | AT-03, AT-04 |
| M3 — Minutes & Privacy | Offline drafts, optional provider, data-egress controls | AT-05–AT-09 |
| M4 — Release | Export, cleanup, packaging, end-to-end checks | AT-11 |

The [v1 product requirements and acceptance criteria](docs/requirements-v1.md) are the source of truth. They contain 14 sections, 39 functional requirements, 8 privacy rules, and 11 acceptance tests. The [M1 OpenSpec change](openspec/changes/windows-recorder-m1/) contains the proposal, design, behavior specs, and 12 implementation tasks.

## Run the M1 recorder

On Windows 10/11 x64, install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the repository root:

```powershell
uv sync
uv run fahmm
```

`uv sync` installs Python 3.12 if needed. Select the speaker output and microphone, then press **Record**. Use **Ctrl+R** to record, **Space** to pause/resume, and **Ctrl+S** to stop. Data is stored under `%LOCALAPPDATA%\fahmm\meetings\<id>` as source WAV chunks, `metadata.json`, and a final `recording.wav`. After an unexpected shutdown, reopen the app and use **Incomplete recordings → Recover selected recording**.

M1 records audio only. Transcription and minutes are planned for later milestones. The implementation separates the [UI](src/fahmm/ui.py), [session controller](src/fahmm/controller.py), [audio adapter](src/fahmm/audio.py), and [storage](src/fahmm/storage.py).

## Development and current status

OpenSpec 2.0 is configured for Codex in `.agents/skills/`, with project context in `openspec/config.yaml`:

```powershell
openspec list
openspec status --change windows-recorder-m1
openspec validate windows-recorder-m1 --strict
uv run pytest
uv run ruff check .
```

The M1 implementation is **10/12 tasks complete**. Automated tests and a short user-triggered Record → Stop test produced a valid stereo WAV. Full M1 acceptance remains open: a permitted 20-minute Teams/Meet recording with both sources audible, Pause/Resume on real hardware, and recovery after terminating a live recording. See [M1 verification](docs/m1-verification.md) and [project status and next steps](docs/project-status.md). M2–M4 have not been implemented.

Do not label v1 privacy-first until its network-egress acceptance tests pass. Application code is licensed under [MIT](LICENSE); dependency and model licenses must be reviewed before release.
