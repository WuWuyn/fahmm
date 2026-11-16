# Proposal: Flow 1–2 review gates and architecture controls

## Why

fahmm has implemented substantial Flow 1 (Record → transcript → playback) and Flow 2 (minutes → optional provider AI → action suggestions) functionality. Existing OpenSpec implementation checklists and successful controlled test runs do not prove real hardware acceptance, complete action-item management, or final distribution readiness. Without explicit, auditable gates, later architecture changes could obscure these distinctions.

## What Changes

- Add a traceable **quality-gate policy** requiring each claim of completion to link requirements, code, tests, environment, evidence and named sign-off.
- Define Flow 1 acceptance scenarios for deliberate dual-source capture, Pause/Resume, crash recovery, offline Vietnamese ASR, edited transcript persistence and timestamp playback.
- Define Flow 2 acceptance scenarios for source-linked extractive minutes, immutable prior approved versions, privacy-mode enforcement and per-send provider disclosure.
- Mark independent action-item management as a **new, unimplemented capability**. Define its desired contract, but do not claim current minutes action entries satisfy it.
- Add architecture guardrails for React ↔ Rust ↔ Python protocol changes, privacy ownership, durable storage/versioning and long-running jobs.
- Define explicit sequencing: automated subsystem verification, real-device verification and cross-flow end-to-end acceptance are separately scored.

This package introduces **review/specification artifacts only**. Implementation, migrations, GUI changes, API integration and GitHub workflow changes need separate approved changes.

## Capabilities

### New Capabilities

- **quality-gate-evidence:** Evidence states, acceptance conditions, cross-flow blocking rules.
- **flow1-acceptance:** End-to-end recording/transcription/playback verification, especially real hardware.
- **flow2-acceptance:** Minutes provenance, disclosure enforcement and full action lifecycle distinction.
- **architecture-guardrails:** Cross-process contract, mutation safety and staged evolution.

### Existing Capabilities

This change adds verification criteria to existing features; it does not replace the M1/M2/M3/M4 or Tauri migration specs. Existing FR/AT requirements remain authoritative. In a conflict, reconcile source requirements explicitly before changing code or declaring a pass.

## Scope and Constraints

- Platform for current release acceptance: Windows 10/11 x64, local-first, no required account, server, API key or GPU.
- Restricted data shall never be sent externally. Local minutes without an LLM remain extractive, not semantic AI.
- Do not block controlled M2/M3 testing merely because G1 live hardware evidence remains open; do block whole-journey acceptance.
- Flow 3 workspace/search, Flow 4 SDK/diarization/integrations and Flow 5 mobile/sync/team are **future proposals**, not implicit v1 requirements.

## Impact

- Review traceability: docs/requirements-v1.md, docs/project-status.md and M1/M2/M3/Tauri verification documents.
- Code review boundaries: desktop/src/shared/bridge, desktop/protocol/contract.json, desktop/src-tauri/src, src/fahmm/bridge, src/fahmm/controller.py, asr_jobs.py, transcripts.py, minutes_store.py and cloud_minutes.py.
- No production file format or API changes in this proposal.
