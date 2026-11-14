# Proposal

## Why

fahmm's working Python core is coupled to a PySide6 interface, while the chosen v1 frontend is React, TypeScript, Vite, and Tauri. A defined desktop layout and process boundary are needed before replacing screens so the migration preserves existing recording, offline processing, and privacy behavior.

## What Changes

- Add a `desktop/` Tauri application containing the React frontend, a small Rust host, and a supervised local Python sidecar. Keep `src/fahmm/` as the Python processing package; introduce a narrow bridge package instead of moving all core modules at once.
- Define a versioned, typed request/response and progress protocol over the sidecar's standard streams. The frontend calls named Tauri commands; Rust owns sidecar startup, shutdown, and message routing. No localhost API is required.
- Replace the PySide6 Recorder, Meetings, Models, and Settings screens with the desktop frontend while preserving their v1 workflows, local data formats, privacy rules, and English UI with Vietnamese-first processing.
- Make local playback, waveform access, file selection/export, recording state, long-running jobs, errors, and cloud-send confirmation work across the new boundary without exposing arbitrary managed file paths or provider credentials to the webview.
- **BREAKING (developer entry point):** The supported desktop launch/build path moves from `uv run fahmm` and a Qt window to the Tauri application after parity is verified. Existing user meeting data remains readable; the Qt entry point stays available during migration and is retired only at cutover.
- Keep M4's completed export and activity-gate service work. Reconcile its remaining Qt UI and PyInstaller/Qt distribution tasks in that change before treating a Tauri build as the release artifact; this proposal does not claim M4 acceptance.

## Capabilities

### New Capabilities

- `desktop-workflows`: The four-screen desktop interface exposes the existing record, meeting review, model, settings, export, and privacy workflows with clear state and failure handling.
- `local-backend-bridge`: The Tauri host and Python sidecar exchange bounded, typed local commands and progress while preserving process lifecycle and server-side privacy checks.

### Modified Capabilities

None. There are no main OpenSpec capability specs yet; the existing M1–M4 change specs and `docs/requirements-v1.md` remain behavioral inputs to this migration.

## Impact

- Adds `desktop/` (Vite/React and `src-tauri/`), `src/fahmm/bridge/`, contract and integration tests, and development/build tooling. Existing Python services, storage schemas, and `%LOCALAPPDATA%/fahmm` data root remain the source of truth.
- Replaces Qt-specific modules such as `ui.py`, `meetings_page.py`, `minutes_panel.py`, `models_page.py`, `settings_page.py`, `playback.py`, and `export_dialog.py` at cutover; the Python core and its tests remain.
- Adds Node, Rust, and Tauri dependencies alongside the existing Python environment. The Windows packaging plan must account for the Tauri host, Python sidecar, and the sidecar's spawned ASR worker.
- Affects the pending M4 Windows distribution design and Qt UI tasks; those artifacts need explicit reconciliation rather than silently marking them complete.
