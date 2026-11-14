# Design

## Context

See `proposal.md` for motivation and the `desktop-workflows` and `local-backend-bridge` specs for observable behavior. The repository currently has one Python package under `src/fahmm/`. `controller.py`, `asr_jobs.py`, `storage.py`, `transcripts.py`, `minutes_store.py`, `cloud_minutes.py`, and other processing services are mostly independent of Qt. `ui.py`, `meetings_page.py`, `minutes_panel.py`, `models_page.py`, `settings_page.py`, `playback.py`, `export_dialog.py`, and the current `app.py` entry point depend on PySide6. `ASRJobController` already spawns a Python worker. M4 is in progress; its completed export and activity-gate services are reusable, but its pending GUI and portable-build design assumes Qt.

## Goals / Non-Goals

**Goals:**

- Establish one clear ownership boundary: React presents state, Rust hosts and supervises, Python owns meeting operations, persistence, and content-egress policy.
- Permit screen-by-screen migration with the existing Qt application still runnable until a verified cutover.
- Make the local protocol, media access, process failure, and Windows build inputs testable independently of visual components.

**Non-Goals:**

- Rewrite recording, ASR, minutes, provider transport, or stored meeting schemas in Rust or TypeScript.
- Introduce a local HTTP server, remote backend, web deployment, account, or sync service.
- Complete M4 deletion, license review, portable release acceptance, or M1 real-hardware acceptance in this change.

## Decisions

### 1. Keep the Python package in place; add a self-contained desktop application

Use this target layout. Existing Python modules remain flat during the first migration pass; moving them into new internal packages is optional only after bridge and regression tests are stable.

```text
fahmm/
  desktop/
    package.json, vite.config.ts, tsconfig.json
    src/
      app/                    # router, application shell, theme, navigation
      features/
        recorder/
        meetings/
        transcript/
        minutes/
        models/
        settings/
      components/ui/          # shadcn/ui primitives
      shared/bridge/          # typed client, DTOs, event adapters
      styles/
    src-tauri/
      src/                    # command registration, sidecar supervisor, media access
      capabilities/
      binaries/               # generated platform-specific sidecar, not source
      tauri.conf.json
  src/fahmm/
    bridge/                   # sidecar entry, protocol, dispatch, service adapters
    ...                       # existing Python services, then temporary Qt modules
  tests/                      # existing Python suite plus bridge contract tests
  docs/, openspec/, scripts/
```

`desktop/` owns the Node lockfile and frontend tests; `desktop/src-tauri/` owns Cargo files and Tauri permissions; root `pyproject.toml` and `uv.lock` continue to own Python. Feature folders hold screen-specific views and hooks; shared UI primitives and the bridge client do not import Python internals. The Python `bridge/` calls services rather than allowing webview code to read storage directly. Tauri's documented project structure places its Rust project in `src-tauri/` beside the frontend. [Tauri project structure](https://v2.tauri.app/start/project-structure/).

**Alternative:** Move all Python code into a new `backend/` tree first. That would change imports, spawned-worker loading, and many tests without proving the new interface, so it is deferred.

### 2. Rust supervises one Python sidecar over framed standard streams

The user selected a sidecar rather than a localhost API. Rust launches one sidecar, keeps its child handle, performs a version/capability handshake, correlates requests, and reports exit or timeout. The webview receives only named Tauri commands; it is not granted a generic shell/execute permission. Python reserves stdout for newline-delimited UTF-8 JSON frames and writes sanitized diagnostics to stderr. Frames carry protocol version, request ID, operation, payload, and either result, event, or structured error. Enforce a maximum frame size, field validation, and an operation allowlist; paginate large transcript reads and limit progress payloads. A malformed frame cannot invoke a service.

Long-running operations return a job ID promptly; Rust forwards small progress/state updates through Tauri channels or events, and the frontend refreshes authoritative snapshots after reconnect. The bridge uses the existing controller/job objects in one process so each recording, model download, and ASR job has one owner. On sidecar loss, Rust fails pending calls and shows a disconnected state. It does not automatically replay mutating requests; a deliberate restart reopens storage and checks recovery. Tauri documents commands, channels, and bundled sidecars for this boundary. [Tauri commands and channels](https://v2.tauri.app/develop/calling-rust/), [sidecars](https://v2.tauri.app/develop/sidecar/).

**Alternative:** A loopback HTTP server would be familiar but introduces a listening port, token and origin management, and a second networking surface for a single-user offline app.

### 3. Define operation contracts around user intentions, not file operations

Start with typed operations for device enumeration and recording controls; meeting list/detail/import; transcription start/cancel/status and transcript save; minutes create/review/approve; model catalog/download/delete; provider profile management; cloud preview/confirm/send; and saved export. The Rust layer validates envelope shape and routes commands; Python validates identifiers, state transitions, privacy, paths, and persisted data again. Errors use stable codes plus safe user-facing messages, with no raw transcript, API key, or exception body in logs. Client DTOs are generated from or checked against one versioned protocol schema so TypeScript, Rust, and Python do not drift silently.

Cloud preview creates a server-held immutable snapshot identified by an opaque short-lived ID. The webview receives the exact preview and returns only the ID and the user's decision; Python rechecks meeting mode and payload, then consumes one authorization at send start. A retry creates a fresh snapshot. This retains the existing `CloudMinutesService` as the only content-egress gate. Zustand stores interface state and cached view data, never the authoritative privacy mode or authorization token.

**Alternative:** Expose generic Python method names or writable file paths to the frontend. That would couple the UI to internals and bypass service-level invariants.

### 4. Give audio playback a narrow media capability

For a selected meeting, Python validates the meeting ID and resolves its owned audio. Rust creates a short-lived media ticket bound to that meeting and serves only that audio through a dedicated local custom protocol with byte-range support. The webview gets the ticket URL, not an arbitrary filesystem path. Python supplies bounded waveform peaks derived from local audio; WaveSurfer consumes those peaks and the ticketed media. For an imported format the Windows webview cannot play, Python decodes to a managed temporary playback cache that is removed on meeting deletion or cache cleanup. Test 30–60-minute files without loading an entire PCM stream into the JavaScript heap.

The broad Tauri asset-file scope is avoided because it can expose every matching file in a directory to the webview. Tauri supports custom URI handlers and documents the breadth of asset protocol scopes. [Custom URI handler API](https://docs.rs/tauri/latest/tauri/struct.Builder.html), [asset protocol scope](https://v2.tauri.app/security/asset-protocol/).

**Alternative:** Send full audio as base64 JSON or allow the webview to construct file URLs. The former is too large; the latter weakens path isolation.

### 5. Keep OS dialogs and secrets outside the webview

Rust invokes native file selection for import and export and retains the selected path; Python performs the existing import/export service checks and writes. The webview gets a display name and operation result, not a general file grant. Windows Credential Manager remains the secret store. Settings reads redacted profiles; keys are submitted only for explicit save/update and are not returned. The Tauri capability file grants only required dialog and host operations; no broad filesystem or shell access is added to the frontend.

**Alternative:** Give React direct filesystem and provider access. That would duplicate validation and weaken the existing privacy boundary.

### 6. Replace Qt by workflow, preserving independent tests

Build the app shell, dark/light tokens, collapsible sidebar, and four routes first; use the chosen Tailwind CSS v4, shadcn/ui, Lucide, Motion, React Router, Zustand, and WaveSurfer dependencies where needed. Then port Recorder, Meetings (including transcript/minutes review), Models, and Settings against the bridge. Reuse Python service tests; add protocol contract tests, Rust process tests, and a small number of desktop end-to-end tests for recording state, offline flow, cloud preview/cancel, and sidecar crash/recovery. Do not treat a screenshot or a disabled button as evidence for Restricted-mode enforcement.

Keep Qt and the old entry point operational during migration. Remove the PySide6 dependency and Qt-only modules only after feature parity, backend privacy tests, media behavior, and Windows startup/worker smoke pass. The final desktop build must package a Python sidecar with `multiprocessing.freeze_support()` before loading ASR modules; this change proves the bundled sidecar starts and can spawn an ASR worker, while M4 owns final portable archive, notices, and release acceptance. M4's remaining Qt-specific tasks and distribution design must be revised explicitly before release rather than assumed complete.

**Alternative:** Delete Qt at scaffold time. That would remove the current usable interface before the new one has parity.

## Risks / Trade-offs

- [A sidecar crash leaves the webview showing stale job success] → Fail pending requests, mark the session disconnected, reload durable snapshots on restart, and show recording recovery only for committed chunks.
- [The sidecar's ASR child process fails in a frozen build] → Smoke the packaged sidecar and an actual spawned ASR worker on Windows before Qt cutover.
- [Cloud preview and send drift across IPC] → Keep snapshot and single-use authorization in Python, recheck classification at send start, and test direct bridge calls in Restricted mode.
- [Large transcripts or audio stall the bridge] → Paginate transcript reads, cap JSON frames, use progress events and ticketed byte-range media, and test long recordings.
- [A custom media URL escapes its meeting scope] → Use opaque expiring tickets, validate meeting IDs and canonical paths, and test traversal, stale ticket, and other-meeting access.
- [M4's pending Qt packaging conflicts with the new entry point] → Reconcile its planning artifacts and keep release status pending until the Tauri distribution path is tested.

## Migration Plan

1. Add `desktop/` and `src/fahmm/bridge/` without changing existing meeting data or the `uv run fahmm` Qt launch path.
2. Implement and test the protocol and sidecar lifecycle against existing Python services; verify no listening port and no content-egress policy bypass.
3. Port screens one at a time, compare behavior with the existing Qt app and v1 requirements, and retain the old UI as a fallback during development.
4. Prove Windows sidecar packaging, ASR worker spawn, media playback, and offline/privacy flows. Reconcile M4's remaining UI and distribution plan before declaring a Tauri release candidate.
5. Switch the supported desktop entry point only after parity checks. Keep the `%LOCALAPPDATA%/fahmm` data root and schemas unchanged so the previous Qt build can reopen data on rollback; do not run both applications against the same data root concurrently.
