# Spec Delta

## Purpose

Defines the local communication and lifecycle guarantees between fahmm's desktop host and Python processing core, including failure recovery and privacy enforcement across the process boundary.

## ADDED Requirements

### Requirement: Compatible local session
The desktop host SHALL start a local Python processing process and establish a compatible protocol session before enabling processing actions. The bridge SHALL require no account, cloud service, or listening network port.

#### Scenario: Compatible startup
- **WHEN** the desktop application starts with a compatible Python sidecar available
- **THEN** the host establishes a local session and enables actions supported by that sidecar's protocol version

#### Scenario: Incompatible sidecar
- **WHEN** the host and sidecar cannot agree on a supported protocol version
- **THEN** the application reports the incompatibility and does not dispatch processing commands

### Requirement: Named operations have correlated outcomes
The bridge SHALL accept only defined operations with validated inputs and SHALL associate each accepted request with one result or a terminal error. It SHALL reject unknown operations and malformed requests without executing them.

#### Scenario: Unknown operation
- **WHEN** a caller sends an operation name the sidecar does not support
- **THEN** the sidecar returns a structured unsupported-operation error and performs no meeting action

#### Scenario: Concurrent requests
- **WHEN** two allowed requests are pending at the same time
- **THEN** each response identifies its own request so the caller cannot mistake one result for the other

### Requirement: Long-running work reports bounded progress
The bridge SHALL provide state or progress updates for recording, model download, transcription, and minutes work without blocking the interface. Cancel requests SHALL target the intended active job and the final state SHALL be observable.

#### Scenario: Cancel transcription
- **WHEN** the user cancels an active transcription
- **THEN** the corresponding job reaches a canceled or completed terminal state and a previously saved transcript remains available

### Requirement: Sidecar failure is visible and recoverable
The desktop host SHALL detect sidecar exit or unresponsiveness, stop accepting commands for that session, and report a recoverable error. Restart SHALL inspect durable local state rather than claiming an interrupted operation succeeded.

#### Scenario: Sidecar exits during recording
- **WHEN** the sidecar exits unexpectedly while recording
- **THEN** the interface reports the lost processing session and, after restart, offers recovery for committed recording chunks

### Requirement: Backend owns privacy authorization
The Python processing core SHALL remain the authority for meeting privacy classification, reviewed transcript selection, per-send cloud authorization, and provider transport. A frontend label or command SHALL NOT bypass those checks.

#### Scenario: Restricted request is rejected
- **WHEN** a cloud-generation command targets a Restricted meeting, including a command sent outside the normal UI flow
- **THEN** the backend rejects it before any meeting-content network request

#### Scenario: Repeated cloud send
- **WHEN** a previously confirmed provider request is retried
- **THEN** the backend requires a new preview and a new single-use confirmation for that send

### Requirement: Sensitive resources cross the boundary by capability
The interface SHALL receive only the meeting data and media needed for the selected action. It SHALL NOT receive provider secrets or unrestricted read/write access to managed meeting and model directories.

#### Scenario: Play selected meeting audio
- **WHEN** the user plays audio for a selected meeting
- **THEN** the application supplies playable local media for that meeting without granting the interface arbitrary filesystem access

#### Scenario: Read provider profile
- **WHEN** Settings displays a saved provider profile
- **THEN** it shows non-secret configuration and does not disclose the stored API key
