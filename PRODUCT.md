# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

fahmm is a Windows 10/11 x64 desktop product. Its interface uses web technology inside Tauri; this platform value describes the interface design language, not a browser deployment.

## Stack

The frontend uses React, TypeScript, and Vite, with Tauri as the desktop shell. The UI foundation is Tailwind CSS v4, shadcn/ui, and Lucide React. Motion handles restrained animation, Zustand stores local interface preferences, WaveSurfer.js renders meeting audio, and React Router handles navigation. Themes use CSS variables and support dark and light modes.

The Tauri desktop interface replaces PySide6 and communicates with the retained Python processing core through a bundled stdin/stdout sidecar. The former Qt interface is kept separately for rollback and regression checks.

## Users

Primary users are individuals who regularly meet in Zoom, Google Meet, Teams, or another Windows audio app, handle internal information, and need to capture outcomes without taking notes throughout the meeting. They may also import recordings from a phone or an in-person meeting.

## Product Purpose

fahmm is a free, open-source, local-first meeting recorder and minutes tool with Vietnamese-first speech processing. A user can record or import audio, transcribe it locally, review and correct the transcript, create a source-linked offline minutes draft or an explicitly authorized provider draft, review the minutes, and export them. Recording and transcription should remain useful without an account, subscription, API key, server, or powerful GPU.

## Positioning

fahmm captures Windows system audio and microphone audio without adding a meeting bot. Its default restricted mode keeps meeting content on the device. Cloud minutes are an optional, per-meeting and per-send decision with the destination and exact outgoing content shown before confirmation.

## Operating Context

- The four top-level areas are Recorder, Meetings, Models, and Settings. The interface language is English; Vietnamese is the default transcription and minutes language.
- The core sequence is Record/Import → Stop and save → Transcribe locally → Review transcript → Draft minutes → Review and export.
- The recorder selects system output and microphone devices, shows elapsed time and recording state, and supports pause, stop, and recovery after an unexpected shutdown.
- Meetings contain audio playback, timestamped transcript review, editable minutes, source references, and export. Models are downloaded explicitly and then used offline. Settings contain optional provider profiles.
- Meeting data is stored locally under `%LOCALAPPDATA%\fahmm\meetings\<id>`.

## Capabilities and Constraints

- Every new meeting defaults to Internal/Restricted. In that mode, fahmm sends no audio, transcript, minutes, or meeting context to an external endpoint and never falls back automatically to cloud processing.
- Cloud-permitted meetings may send only reviewed, selected transcript content after the user confirms each request. Audio is not uploaded automatically. Provider errors must preserve local work.
- Offline minutes without a local summarization model are an extractive, source-linked draft, not a complete semantic summary. Drafts require review; missing owners, dates, or decisions must not be invented.
- The frontend has a collapsible sidebar, a clear recording indicator, and a persistent, legible privacy badge that distinguishes local-only processing from cloud permission. Audio waveforms and transcript editing use purpose-built components; shadcn/ui is the shared component foundation.
- v1 excludes real-time transcription, speaker diarization, meeting bots, cloud sync, mobile apps, and automatic distribution of minutes.
- Existing Python capture, transcription, storage, and minutes behavior remains in the bundled sidecar. The Tauri host starts the sidecar and uses a versioned JSON-lines protocol over standard streams.

## Brand Commitments

- Preserve the name **fahmm** (Fah Meeting Minutes) and its free, open-source, privacy-first position.
- The user has specified dark mode by default, a graphite/slate palette with a blue accent, subtle borders and shadows, and restrained animation. Light mode must also be available.

## Evidence on Hand

- `docs/requirements-v1.md` is the v1 requirements and acceptance-criteria source of truth; `docs/user-flow.md` describes the current desktop workflow.
- `README.md` and `openspec/config.yaml` state the product scope and privacy rules. The current desktop entry is `desktop/` with a Python bridge in `src/fahmm/bridge/`.
- M1–M3 implementation and verification notes exist in `docs/`; release work remains in the M4 OpenSpec change. The Tauri migration and its development-host verification are recorded in `docs/tauri-verification.md`.

## Product Principles

1. Keep meeting content local by default and make every external send an informed user action.
2. Preserve a useful offline path from recording through a reviewable minutes draft.
3. Make the record → transcribe → review → minutes sequence clear without requiring technical setup beyond an explicit model download.
4. Treat transcripts and generated minutes as editable evidence, with source timestamps and visible uncertainty.
5. Keep the desktop interface focused on the four v1 areas and avoid unnecessary UI frameworks.
