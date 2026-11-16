# fahmm v1 — Product Requirements and Acceptance Criteria

fahmm (Fah Meeting Minutes) records meetings, transcribes speech, and helps write meeting minutes in Vietnamese. It serves people who meet often, want less manual note-taking, do not want another subscription, and need to protect internal information.

**Status:** Proposed v1.0 specification, 14 November 2026. **Acceptance platform:** Windows 10/11 x64. **Direction:** free, open source, and local-first. No mandatory backend or account.

> **Non-negotiable principle:** For an Internal/Restricted meeting, the app must not send audio, transcripts, minutes, or meeting context to any external endpoint. Without a local summarization model, it must produce only a source-linked extractive draft and must not present that draft as a complete AI summary.

# 1. Goals and success measures

**Problem:** Participants have to discuss and take notes at the same time. Existing tools often require a bot, account, subscription, cloud upload, or unnecessary real-time processing.

**v1 outcome:** Without using a command line, a person can Record/Import → transcribe Vietnamese locally → review and edit the transcript → produce an offline minutes draft or an authorized provider summary → export Markdown.

**Success criteria**

- Record both other participants' system audio and the user's microphone without a meeting bot.
- Transcribe a Vietnamese recording after the meeting, including offline when the model is already downloaded.
- Send no meeting content outside the device in Internal/Restricted mode, verified with a blocked-network test.
- Produce structured Vietnamese minutes that distinguish confirmed information from items requiring review.
- Require no account, subscription, GPU, or paid API for recording and transcription.

# 2. Users, environment, and scope

**Primary users:** Individuals handling internal information in Zoom, Google Meet, Teams, or another Windows audio app, and sometimes importing recordings from a phone or in-person meeting.

**In scope for v1 (P0):**

- Windows desktop app with English and Vietnamese interfaces and Vietnamese-first speech processing. English remains the initial interface language until the user switches it.
- Simultaneous system audio and microphone recording; Record, Pause/Resume, Stop; local files.
- Import of common audio formats.
- Local Whisper transcription after Stop, with timestamps and a previously downloaded Hugging Face model.
- Basic model management: select, download, view size, and delete.
- Transcript review/editing and minutes generation under two privacy modes.
- One or more configurable OpenAI-compatible endpoints for authorized use.
- Markdown minutes and TXT transcript export; review and deletion of recordings.

**Out of scope for v1:**

- Real-time transcription, speaker diarization, or speaker identity recognition.
- Meeting bots, automatic calendar detection, or automatic email/Slack delivery.
- Mobile app/PWA, multi-device sync, public server, or team accounts.
- Guaranteed system-audio recording on macOS/Linux; only an extensible architecture is planned.
- A high-quality private semantic AI summary without either a local LLM or an authorized internal service.

# 3. User workflow

Record or import audio → save locally → transcribe with local Whisper → review/edit transcript → choose the meeting's data-sharing mode → create a source-linked offline draft or confirm a cloud request → review/edit/export Markdown.

The app opens on the Recorder screen. The user chooses devices and presses Record, then Stop & Process. Speech recognition starts only after audio is saved. If transcription or summarization fails, saved audio and transcripts remain available for retry.

# 4. Recording and import requirements

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-01 | P0 | Record system audio through WASAPI loopback on Windows without a bot or meeting-host permissions. |
| FR-02 | P0 | Record the microphone simultaneously; allow microphone selection and changes before recording. |
| FR-03 | P0 | Provide Record, Pause/Resume, and Stop with a clear elapsed timer and recording indicator. |
| FR-04 | P0 | Save audio locally; retain separate microphone and system tracks during capture where feasible to reduce loss and aid alignment. |
| FR-05 | P0 | Import WAV, MP3, M4A, and FLAC; clearly report unsupported formats. |
| FR-06 | P0 | Recover an unfinished recording after an app crash or unexpected shutdown. |
| FR-07 | P1 | Support per-source gain, pre-recording signal checks, and device changes during a session. |

**Default behavior:** Do not record automatically, record secretly in the background, or activate the microphone before the user presses Record. Remind users to follow recording policies and obtain consent when needed.

# 5. Local transcription and Vietnamese

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-08 | P0 | Use faster-whisper/CTranslate2 for offline recognition from the selected meeting's saved audio, starting at a user-selected time or 00:00 by default and processing through the end of that recording. |
| FR-09 | P0 | Default to Vietnamese (vi), with optional Auto Detect and English modes. |
| FR-10 | P0 | Include source-relative segment timestamps within the recording's duration and support Vietnamese speech mixed with English terms. |
| FR-11 | P0 | Show processing progress, Cancel/Retry, and errors without blocking the UI. |
| FR-12 | P0 | Allow transcript editing before minutes generation; retain the original transcription or a minimal edit history. |
| FR-13 | P1 | Support a custom names/terms dictionary for reruns and SRT export. |

Real-time output is not required. Whisper performs speech-to-text and is not a summarizer. Evaluate transcript quality using actual Vietnamese recordings; do not promise absolute accuracy.

# 6. Hugging Face Model Manager

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-14 | P0 | Recommend multilingual Whisper base, small, medium, and large-v3-turbo when compatible with the backend. |
| FR-15 | P0 | Download selected Hugging Face models; show publisher, estimated size, license, and progress. |
| FR-16 | P0 | Reuse cached models offline and allow deletion of unused models. |
| FR-17 | P0 | Accept a custom repository ID only for Whisper models in a CTranslate2 format compatible with faster-whisper. |
| FR-18 | P0 | Check free disk space, handle failed/resumed downloads, and never run repository code or enable trust_remote_code. |
| FR-19 | P1 | Warn about large models on unsuitable RAM/GPU configurations and track model revisions for reproducibility. |

Downloading a model does not mean every Hugging Face model will run. V1 does not support every ASR/LLM architecture or arbitrary checkpoint conversion.

# 7. Vietnamese meeting minutes

**Default output structure**

1. Meeting title and date, using an explicit Vietnamese unknown marker when information is absent.
2. Main summary.
3. Topics and discussion points.
4. Agreed decisions.
5. Action items: task, owner, due date, and verification status.
6. Open questions and follow-ups.
7. Transcript timestamps for important conclusions.

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-20 | P0 | Write minutes in Vietnamese by default, even when the transcript contains English terminology. |
| FR-21 | P0 | Allow draft review/editing, prompt/template editing, and regeneration without overwriting an approved version. |
| FR-22 | P0 | Do not invent owners, deadlines, decisions, or attendees; show an explicit Vietnamese unknown marker when data is absent. |
| FR-23 | P0 | Mark drafts "Unverified" and allow opening their source segments. |
| FR-24 | P0 | Support OpenAI-compatible API minutes generation for meetings authorized to share data. |
| FR-25 | P0 | In Restricted mode, create a source-linked offline extractive draft from segments/keywords; do not label it a complete AI summary. |
| FR-26 | P1 | Optionally support a lightweight local summarizer or an organization-approved internal endpoint; neither is required by default. |

**Product limit:** If content cannot leave the device and no local LLM is available, v1 can only produce a basic extractive/template draft. High-quality semantic summarization needs a model running within approved infrastructure.

# 8. Data classification and network policy

| Mode | Default | Permitted outgoing content | Minutes generation |
| --- | --- | --- | --- |
| Internal/Restricted | Yes, for each new meeting | No audio, transcript, meeting-content prompt, or minutes to external endpoints | Offline draft; trusted local engine is optional |
| Cloud permitted | User changes it manually | Only selected/approved transcript content, after confirmation for each send | Configured OpenAI-compatible provider |

**Mandatory privacy rules**

- PR-01: Each new meeting defaults to Internal/Restricted. Closing/reopening the app or an API error must not change the mode.
- PR-02: Internal/Restricted mode blocks every network request that processes meeting content. Never fall back automatically from local processing to cloud.
- PR-03: Before each cloud send, show the destination hostname, data types, and warning; require separate confirmation for each meeting/send.
- PR-04: Never upload audio automatically for summarization. When cloud is authorized, send only the transcript content the user reviewed/selected.
- PR-05: Model download is separate: the app may contact Hugging Face for weights, but must not attach audio or meeting content.
- PR-06: No telemetry, analytics, crash reports, auto-sync, or auto-update that uploads meeting content without a clear user choice.
- PR-07: Keep conversation content and API keys out of logs. Provide deletion of recordings, transcripts, minutes, and temporary files.
- PR-08: In Restricted mode, do not call an external service merely to test connectivity.

Restricted mode is a promise about data flows controlled by fahmm, not a substitute for OS security policy or assessment of third-party models/plugins.

# 9. OpenAI-compatible provider configuration

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-27 | P0 | Support multiple provider profiles with Name, Base URL, API key, Model ID, and timeout. |
| FR-28 | P0 | Use the OpenAI Python SDK with a custom Base URL for compatible chat/completions calls. |
| FR-29 | P0 | Store API keys in the OS secret store, such as Windows Credential Manager, never in plain settings or logs. |
| FR-30 | P0 | Require no API key for recording, import, transcription, or offline drafts. |
| FR-31 | P0 | Default to HTTPS; permit HTTP only on loopback localhost and never disable TLS verification automatically. |
| FR-32 | P0 | Preserve audio/transcripts and provide retryable errors for quota, timeout, unsupported response format, or lost network. |
| FR-33 | P1 | Offer template/prompt selection, token limits, and a preview of content to be sent. |

Do not assume every OpenAI-compatible provider supports JSON Schema, streaming, or identical parameters. The backend should fall back to text responses, then validate and normalize them. Never include API keys in exports.

# 10. Storage, export, and UI

| ID | Priority | Requirement |
| --- | --- | --- |
| FR-34 | P0 | Give each meeting its own folder for audio, transcript, minutes, metadata, and processing status. |
| FR-35 | P0 | List meetings by time, name, and status; reopen them for playback, edits, and reruns. |
| FR-36 | P0 | Export minutes.md and transcript.txt and copy Markdown to the clipboard. |
| FR-37 | P0 | Delete meeting data and temporary files with confirmation; never push them to a cloud account automatically. |
| FR-38 | P0 | Use an English-default UI with a persistent Vietnamese/English switch and Recorder, Meetings, Models, and Settings as the only top-level screens. |
| FR-39 | P1 | Add SRT/DOCX/PDF export, local transcript search, and additional UI languages beyond English and Vietnamese. |

V1 does not depend on a database/server. JSON metadata and the file system are the source of truth. SQLite can be added if search or history management becomes complex.

# 11. Non-functional requirements

- **Resources:** Run on Windows 10/11 x64 with ordinary CPU/RAM (minimum test configuration: 8 GB); no mandatory GPU. Warn before using large models on insufficient hardware.
- **Reliability:** Write audio in chunks and flush regularly; offer recovery after an app crash. Keep recording and AI work off the UI thread.
- **Maintainability:** Use adapters for AudioCapture, ASRBackend, and SummarizerProvider so libraries can change without rewriting the UI.
- **Packaging:** Provide a Windows installer or portable build with a checksum and clear instructions; end users must not need to install Python manually.
- **Observability:** Log only technical events with sensitive information removed; viewing logs must never expose transcripts/audio.
- **Accessibility:** Support keyboard control, a visible recording indicator, and clear interface error messages in the selected language; retain technical details when needed for diagnosis.
- **Cost:** Local recording/STT are free to use; API summarization may cost money only when a user configures and invokes a provider.
- **Licensing:** Aim for MIT/Apache-2.0 application code after reviewing dependency and model licenses.

# 12. v1 acceptance criteria

| Test | Action | Pass condition |
| --- | --- | --- |
| AT-01 | Record a 20-minute Teams/Meet meeting on Windows with headphones and a microphone | Playback clearly contains both sources; no bot joins. |
| AT-02 | Press Record/Pause/Resume/Stop | Timer and indicator are correct; audio file is valid; nothing is recorded before Record. |
| AT-03 | Import a 30–60 minute Vietnamese file offline with an already downloaded model | Timestamped transcript is created without an API key and UI stays responsive. |
| AT-04 | Download, select, and delete a Whisper model from Hugging Face | Progress and cache work; incompatible repositories are rejected safely. |
| AT-05 | Record a meeting, disconnect internet, and use Restricted mode | Recording, local STT, and offline draft still work; no network request carries meeting content. |
| AT-06 | Attempt cloud summarization in Restricted mode | Request is blocked with an explanation and nothing is sent. |
| AT-07 | Switch a meeting to cloud-permitted mode and call a provider | Hostname/payload warning appears, data is sent only after confirmation, and Vietnamese minutes are created. |
| AT-08 | Provider times out or returns an error | Audio/transcript remain intact; user can retry or change provider. |
| AT-09 | Transcript contains no owner or deadline | Minutes use a Vietnamese unknown marker, do not invent facts, and link decisions to source timestamps. |
| AT-10 | Kill the app mid-recording, then reopen it | Flushed audio can be recovered without damaging other meetings. |
| AT-11 | Export and delete a meeting | Markdown/TXT open outside the app; deletion requires confirmation and removes that meeting's temporary files. |

In addition to functional testing, check at least three Vietnamese speech cases: Northern accent, Southern accent, and Vietnamese mixed with English terms. Use only recordings approved for testing.

# 13. Implementation roadmap

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M1 — Recorder | Windows UI, system audio + mic, pause/stop, recovery | AT-01, AT-02, AT-10 |
| M2 — Local ASR | Audio import, Whisper, model manager, transcript editor | AT-03, AT-04 |
| M3 — Minutes & Privacy | Offline draft, OpenAI-compatible provider, Restricted/Cloud policy | AT-05–AT-09 |
| M4 — Release | Export, cleanup, packaging, smoke tests | AT-11 and end-to-end tests |

Each milestone must run independently on Windows. Mobile, cross-platform support, and advanced UI must not block a usable v1.

# 14. Decisions to keep explicit

1. **Quality of private offline minutes:** Without cloud or a local LLM, only a limited extractive draft is possible. Better semantic summaries in environments that prohibit egress require a lightweight local model, stronger internal hardware, or an approved internal endpoint.
2. **Recording within organizations:** The app cannot determine whether a meeting may be recorded. Users must follow internal policy and applicable notice/consent rules.
3. **Cross-platform support:** The engine may be reusable, but Windows x64 is the only v1 release target.
4. **Mobile and outside meetings:** V1 imports phone recordings; direct PWA/native mobile recording belongs to a later roadmap.
5. **Definition of done:** Do not release v1 under a Privacy First claim until AT-05/AT-06 egress tests pass.

**Product principle:** Users own their files and know exactly when their data leaves the device.
