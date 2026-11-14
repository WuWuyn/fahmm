# Tauri desktop architecture

The supported desktop development path is React/TypeScript/Vite inside Tauri, with the existing Python processing core as a bundled sidecar. The earlier Qt portable candidate remains available as a rollback build while its separate M4 release planning is reconciled.

## Directory ownership

| Path | Owner | Responsibility |
| --- | --- | --- |
| `desktop/src/app/` | React/TypeScript | Four-area router, navigation, backend availability, and theme controls |
| `desktop/src/features/` | React/TypeScript | Recorder, Meetings/audio, transcript, minutes, Models, and Settings views |
| `desktop/src/components/ui/`, `desktop/src/styles/` | React/TypeScript | shadcn/ui components, Tailwind v4 entry, and graphite/blue theme tokens |
| `desktop/src/shared/` | React/TypeScript | Typed bridge client and local-only Zustand interface preferences |
| `desktop/src-tauri/` | Rust/Tauri | Window, native capabilities, sidecar lifecycle, request routing, and scoped media access |
| `desktop/protocol/` | Shared contract | Version, frame limit, operation DTO shapes, errors, and fixtures |
| `src/fahmm/bridge/` | Python | Local JSON-lines endpoint and adapters to existing services |
| `src/fahmm/*.py` | Python | Recording, ASR, models, storage, minutes, provider policy, and export |
| `src/legacy/qt/` | Optional historical UI | PySide6 screens used only by regression tests and the earlier rollback build; excluded from the normal `fahmm` wheel |
| `tests/` | Python | Existing behavior and bridge contract/integration tests |

The React process does not read meeting directories or call a provider. Rust starts one Python sidecar and communicates through its standard streams. The sidecar opens no listening port. Vite uses a development server for the frontend during `tauri dev`; that is not a meeting-data API. The existing Python services and `%LOCALAPPDATA%\fahmm` remain the authority for stored data and privacy decisions.

## Protocol v1

`desktop/protocol/contract.json` is the versioned source for frame limits, allowed operations, event shapes, and safe error codes. Each wire message is one UTF-8 JSON object followed by a newline. Requests and responses carry the same `id`; model and ASR work use bounded status polling. stdout is reserved for protocol messages; diagnostics are sanitized and use stderr. A host must complete `session.hello` before sending service commands. The contract covers recording, meetings, transcript and minutes versions, models, provider disclosure, exports, and media tickets. A version mismatch disables processing rather than guessing at a format.

The Tauri host owns native import and export dialogs. The webview cannot submit a path to import, export, or media resolution. Audio is served through a meeting-bound, expiring ticket on the `fahmm` custom protocol with bounded byte ranges. Python resolves the ticket against its managed meeting directory; the webview receives no audio path or provider key. Cloud preview and single-use confirmation stay in Python.

## Source-mode setup and launch on Windows

From the repository root:

```powershell
uv sync
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
cd desktop
npm ci
npm run build
npm run tauri dev
```

The Tauri host starts `.venv\Scripts\python.exe -m fahmm.bridge` from the repository root in source mode. Rust and the Visual Studio C++ build tools are required for `tauri dev`. Run `cargo check` from `desktop/src-tauri` to check Rust independently. For a bundled build, run `uv run --locked python scripts/build_sidecar.py` from the root, then `npm run tauri build` from `desktop/`; Tauri's `externalBin` includes the generated sidecar. The release host starts that binary next to the Tauri executable and does not require a separately installed Python.

To inspect the source-mode handshake without opening either UI, send the following two lines to `uv run python -m fahmm.bridge` from the repository root. Use a temporary `LOCALAPPDATA` directory when testing so the command does not use personal meeting data.

```json
{"v":1,"kind":"request","id":"hello","op":"session.hello","params":{"versions":[1]}}
{"v":1,"kind":"request","id":"health","op":"system.health","params":{}}
```

The response lines must have matching IDs, select protocol version 1, and report `{"status":"ready"}` for health. The sidecar exits when stdin closes. No provider request or model download occurs during this check.

## Development guardrails

- Keep generated `node_modules/`, `dist/`, and Rust `target/` out of Git; keep `package-lock.json` and `Cargo.lock` in Git.
- Keep every cloud-content request behind the Python disclosure service. A privacy badge or disabled frontend button is not an authorization boundary.
- Add named bridge operations and corresponding shared fixtures before attaching a new screen control.
- The legacy Qt source is only for regression tests and rollback checks. Run those tests with `uv run --locked --extra legacy-qt pytest`; the Tauri sidecar build excludes Qt.
