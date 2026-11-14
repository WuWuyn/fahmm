# Spec Delta

## Purpose

Keep each meeting's disclosure choice explicit and persistent, and prevent meeting content from leaving the device unless the user deliberately authorizes a specific send.

## ADDED Requirements

### Requirement: Restricted by default and persistent
Every new or legacy meeting without a valid classification SHALL be treated as Internal/Restricted. A user SHALL be able to change a meeting to Cloud permitted and back. The chosen mode SHALL persist across restart, transcription reruns, offline drafting, and provider errors.

#### Scenario: New meeting
- **WHEN** a recording or import creates a meeting
- **THEN** its visible and enforced classification is Internal/Restricted

#### Scenario: Missing or invalid mode
- **WHEN** meeting metadata has no recognized classification
- **THEN** the app treats it as Restricted and blocks cloud minutes generation

#### Scenario: Provider error
- **WHEN** a cloud request fails after a meeting was set to Cloud permitted
- **THEN** the meeting mode remains the user's selected mode and no new disclosure occurs without another confirmation

### Requirement: Restricted egress prohibition
The system MUST block every network request that would process or carry audio, transcript, minutes, or meeting-content prompts for a Restricted meeting. It MUST NOT automatically change classification, fall back to a provider after local failure, or call an external endpoint merely to test connectivity in Restricted mode.

#### Scenario: Direct cloud attempt in Restricted mode
- **WHEN** cloud minutes generation is invoked for a Restricted meeting, including through a non-UI entry point
- **THEN** the request is rejected with an explanation before any network connection carrying meeting content is opened

#### Scenario: Offline generation fails
- **WHEN** offline draft generation fails for a Restricted meeting
- **THEN** the app reports the local error and does not contact a provider

### Requirement: Per-send disclosure and confirmation
For a Cloud permitted meeting, the app SHALL show the destination hostname, data types, warning that content leaves the device, and the exact selected transcript and meeting-content prompt before each provider send. A separate affirmative confirmation SHALL be required for every send, including retry or regeneration, and the enforced mode SHALL be checked again immediately before transmission.

#### Scenario: User declines disclosure
- **WHEN** the user cancels or closes the confirmation preview
- **THEN** no meeting content is transmitted and no cloud minutes version is created

#### Scenario: Retry after a failed send
- **WHEN** the user retries a failed provider request
- **THEN** the app presents a new disclosure preview and requires a new confirmation before sending

#### Scenario: Mode changes before transmission
- **WHEN** the meeting becomes Restricted after preview but before transmission
- **THEN** the send is blocked and no meeting content leaves the app

### Requirement: Minimum outgoing content
Cloud minutes generation SHALL send only the transcript segments the user selected and reviewed, plus the disclosed generation prompt. It MUST NOT upload audio automatically or include unselected transcript runs, other meetings, local file paths, stored minutes, or API keys in the request body.

#### Scenario: Select a subset
- **WHEN** the user selects only some reviewed transcript segments for a cloud request
- **THEN** the preview and transmitted request contain those segments and omit all other meeting content

### Requirement: No implicit content sharing
The app MUST NOT add telemetry, analytics, crash reports, automatic synchronization, or automatic updates that transmit meeting content. Model download MAY contact Hugging Face only after a separate user action and MUST NOT attach meeting content.

#### Scenario: Restricted meeting and model download
- **WHEN** the user explicitly downloads a model while viewing a Restricted meeting
- **THEN** the model request contains no audio, transcript, minutes, or meeting context
