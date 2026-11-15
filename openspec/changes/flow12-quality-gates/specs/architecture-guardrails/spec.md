# Spec Delta

## Purpose

Keep future flows additive and safe across the Tauri/Rust/Python boundary while protecting previously accepted offline and privacy behavior.

## ADDED Requirements

### Requirement: Explicit cross-process contract ownership
New functionality SHALL enter through named operations defined in the versioned desktop protocol contract. Frontend, Rust and Python implementations SHALL agree on operation names, envelope shape, field types, errors and handshake version. Breaking changes SHALL provide compatibility handling or a deliberate version rejection.

#### Scenario: New task or workspace operation
- **WHEN** a developer adds a task, search or context operation
- **THEN** contract DTOs and validation, host permissions, Python service handling, TS client types, and positive/negative cross-language fixtures are reviewed together

#### Scenario: Incompatible protocol version
- **WHEN** the webview or sidecar has an incompatible protocol version
- **THEN** the host rejects the incompatible call with a safe error rather than misinterpreting or replaying the mutation

### Requirement: Single content-egress authority
The Python policy layer SHALL remain authoritative for meeting privacy classification, allowed transcript segments and provider confirmation. UI checks and frontend state SHALL NOT be sufficient to permit egress. No new SDK, search, integration or sync feature may transmit meeting content without a separately specified consent and data-egress boundary.

#### Scenario: UI bypass attempt
- **WHEN** an unauthorized client submits an otherwise well-formed provider or integration request
- **THEN** the domain policy rejects it with zero outbound content transmission

#### Scenario: A future plugin requests meeting text
- **WHEN** a plugin attempts to access Restricted meeting content
- **THEN** access is denied unless an explicitly approved, enforceable local policy covers that capability; a plugin install alone grants no content sharing

### Requirement: Minimal webview and media permissions
The webview SHALL NOT receive arbitrary filesystem access, provider secrets or unvalidated managed data paths. Native dialogs and meeting-scoped, expiring playback tickets SHALL remain host-controlled. Media reads SHALL support bounded ranges and prevent traversal or unrelated-meeting access.

#### Scenario: Forged path or media ticket
- **WHEN** a request names an unmanaged path, expired media ticket or another meeting's resource
- **THEN** the Rust/Python host refuses access and leaves owned data unchanged

### Requirement: Safe long-running operations
Long-running recording/ASR/model/provider operations SHALL preserve UI responsiveness and allow unrelated safe status requests within an agreed, tested latency budget. Blocking work SHALL not silently replay mutations after process restart. Any proposed synchronization redesign SHALL include contention, cancellation and crash tests.

#### Scenario: Slow cloud summarization
- **WHEN** a provider request stalls while a user requests a recording/meeting status
- **THEN** the status request completes within the approved responsiveness budget or the measured limitation is logged as a release blocker before that concurrency feature is claimed

#### Scenario: Sidecar exits mid-mutation
- **WHEN** the Python sidecar terminates during a mutating request
- **THEN** the host reports an uncertain/failed operation, does not automatically replay it, and allows authoritative local-state reconciliation after restart

### Requirement: Durable version and migration invariants
New persisted entities SHALL preserve stable IDs, version/provenance references and atomic local writes; schema upgrades SHALL include rollback or recovery tests for pre-existing meetings. Deleting or editing an original source SHALL not silently rewrite an approved minutes version or independently accepted task.

#### Scenario: Upgrade from a meeting without tasks
- **WHEN** a future task-manager migration opens an older meeting
- **THEN** existing recordings, transcript runs and minutes versions remain readable, and any derived task creation requires explicit user action or a documented migration choice

#### Scenario: Crash during storage write
- **WHEN** the app is terminated while creating a transcript/minutes/task revision
- **THEN** the last valid committed data remains readable, with incomplete staging recoverable or safely ignored

### Requirement: Separate future-flow decisions
Workspace/search/context, diarization/SDK/integrations and mobile/sync/team SHALL each require their own approved OpenSpec change before implementation. Each change SHALL identify data ownership, privacy policy, protocol/API evolution, migration path, negative tests and release scope.

#### Scenario: Proposed cross-meeting search
- **WHEN** search and shared context are requested
- **THEN** the proposal defines whether the index is rebuildable, which meetings are visible, how deletion invalidates results and whether any content leaves the device before implementation starts

#### Scenario: Proposed cloud sync
- **WHEN** multi-device or team sync is requested
- **THEN** identity, authorization, encryption, offline conflicts, deletion, retention and Restricted meeting behavior are specified before server or mobile implementation
