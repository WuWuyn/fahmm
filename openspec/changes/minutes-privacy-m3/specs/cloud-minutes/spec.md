# Spec Delta

## Purpose

Generate reviewable Vietnamese minutes through an explicitly chosen OpenAI-compatible provider after a meeting-specific disclosure decision, without risking local recordings or transcripts.

## ADDED Requirements

### Requirement: Authorized provider generation
The system SHALL allow cloud minutes generation only for a Cloud permitted meeting with a selected provider and an affirmative confirmation for that specific send. The result SHALL be saved as a new unverified local minutes version; it SHALL NOT replace an approved version or automatically change the meeting's privacy mode.

#### Scenario: Confirmed cloud request
- **WHEN** the user selects reviewed transcript content, confirms the disclosed payload, and the provider responds successfully
- **THEN** a new unverified Vietnamese minutes version is saved locally for review

#### Scenario: No confirmation
- **WHEN** the user does not confirm the request
- **THEN** no provider call is made and existing minutes versions remain unchanged

### Requirement: Compatible response handling
The app SHALL accept ordinary text responses from an OpenAI-compatible chat-completions provider as well as structured responses when available, then validate and normalize the result into the minutes review structure. It MUST NOT require JSON Schema or streaming support from the provider.

#### Scenario: Text-only provider
- **WHEN** a compatible provider returns a plain text minutes response
- **THEN** the app creates a reviewable unverified version without requiring a structured-output feature

#### Scenario: Unsupported response
- **WHEN** the provider returns empty or unusable content
- **THEN** the app reports a retryable error and does not replace any saved minutes version

### Requirement: Evidence and uncertainty in cloud minutes
Cloud-generated minutes SHALL use Vietnamese by default, mark missing owner, deadline, attendee, or decision information with `Chưa rõ`, and attach valid source segment timestamps to decisions and important conclusions. Unsupported or unlinked statements MUST NOT be shown as confirmed facts; the whole generated version remains unverified until the user approves it.

#### Scenario: No owner or deadline in selected transcript
- **WHEN** the selected transcript describes an action without an owner or deadline
- **THEN** the minutes show `Chưa rõ` for those fields and link the action to its source timestamp

#### Scenario: Invalid source reference
- **WHEN** a provider response cites a segment outside the selected transcript
- **THEN** the citation is rejected and the associated statement is flagged for review rather than presented as verified

### Requirement: Recoverable provider failures
Quota errors, timeouts, lost connectivity, and incompatible response formats SHALL be reported without deleting or changing audio, transcripts, approved minutes, or the meeting's classification. The user SHALL be able to retry or choose another provider, subject to a fresh disclosure confirmation.

#### Scenario: Provider timeout
- **WHEN** a confirmed provider request times out
- **THEN** the app preserves all local meeting data, displays a useful error, and offers retry or provider selection

#### Scenario: Retry with another provider
- **WHEN** the user chooses another profile after a failure
- **THEN** the app presents the new destination and payload for confirmation before sending
