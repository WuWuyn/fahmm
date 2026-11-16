# Spec Delta

## Purpose

Verify source-linked minutes, local-first privacy and the explicit boundary between candidate actions in a document and independently tracked tasks.

## ADDED Requirements

### Requirement: Honest local extractive minutes
Without a configured local semantic LLM, the offline path SHALL generate source-linked extractive minutes from reviewed local transcript content, SHALL require no account/key/network and MUST NOT present the result as a semantic AI-generated summary.

#### Scenario: Restricted offline draft
- **WHEN** a user generates minutes from a reviewed Restricted transcript while network connections are blocked
- **THEN** a local unverified extractive draft is saved with valid citations and zero content egress

#### Scenario: Product copy describes offline output
- **WHEN** the offline draft is shown or exported
- **THEN** the user can distinguish deterministic extractive suggestions from a complete semantic AI summary

### Requirement: Provenance and unknown information
Minutes SHALL link material decisions, topics, tasks and conclusions to source transcript segment IDs and timestamps. The app MUST NOT invent ownership, dates, attendees or decisions; missing fields SHALL remain explicitly unknown and provider hallucinations SHALL be rejected or flagged for review.

#### Scenario: Unassigned task
- **WHEN** the transcript states an action but no owner or due date
- **THEN** both fields remain “Chưa rõ” and the suggested task links to its source segment

#### Scenario: Invalid provider citation
- **WHEN** a provider supplies an out-of-range segment reference or unsupported personal assignment
- **THEN** the application discards the invalid claim or marks it unverified and never promotes it to approved fact automatically

### Requirement: Non-destructive minutes versions
Draft creation, edit, regeneration and approval SHALL retain earlier approved versions, make the active version explicit and validate source references against the correct transcript run.

#### Scenario: Regenerate after approving
- **WHEN** a user approves minutes and then regenerates from edited transcript content
- **THEN** the system creates a new unverified version and the approved version remains unchanged

#### Scenario: Reopen edited minutes
- **WHEN** the user edits a draft and reopens the meeting
- **THEN** the edit, review state and citations remain available

### Requirement: Server-enforced Restricted mode
Cloud provider access SHALL be denied for Restricted meetings by Python policy even if the webview calls the bridge directly. The app SHALL NOT silently downgrade to a provider when offline generation, ASR or networking fails.

#### Scenario: Direct unauthorized bridge attempt
- **WHEN** a client invokes cloud preparation or send for a Restricted meeting
- **THEN** the service denies the call before any provider connection is attempted

#### Scenario: Offline processing failure
- **WHEN** an offline minutes operation fails
- **THEN** the app retains existing data and does not invoke cloud summarization as an automatic fallback

### Requirement: Exact per-send disclosure
For a Cloud permitted meeting, the user SHALL review the destination and exact selected reviewed transcript content, then explicitly accept or cancel. Authorization SHALL be single-use, bound to current content and policy, expire in a bounded interval and be reissued for each retry. The provider MUST NOT receive unselected segments or a secret in the request payload.

#### Scenario: Cancel preview
- **WHEN** the user previews a provider request and cancels
- **THEN** no outbound request occurs

#### Scenario: Confirm selected content
- **WHEN** the user confirms a fresh preview of a subset of reviewed segments
- **THEN** only those segments and disclosed generation instructions are eligible for the one authorized provider request

#### Scenario: Stale or replayed confirmation
- **WHEN** a segment, profile or privacy classification changes after preview, or the confirmation is reused
- **THEN** the provider call is rejected and a fresh disclosure is required

### Requirement: Failures do not lose reviewed work
Provider timeout, malformed response, cancelled send or backend restart SHALL NOT overwrite the approved minutes version, original transcript or local recording. Sensitive provider errors and credentials SHALL NOT be written to ordinary logs.

#### Scenario: Provider fails after confirmation
- **WHEN** the provider returns an error or times out
- **THEN** the user can retry only after a new confirmation and prior approved local work remains available

### Requirement: Distinguish action suggestions from task management
The project SHALL clearly label action entries inside minutes as **suggestions** until a separate task lifecycle exists. A complete action management feature SHALL persist stable task IDs, ownership, due dates, status changes, source references and review history independently of the minutes text. Automatically extracted suggestions MUST NOT become confirmed assignments without user approval.

#### Scenario: Current minutes-only action entry
- **WHEN** the minutes document contains a task with unknown owner and no separate task entity
- **THEN** the UI may show an action suggestion but SHALL NOT imply that it is assigned, tracked or scheduled

#### Scenario: Future independent task creation
- **WHEN** an explicitly reviewed action suggestion is promoted to a tracked item in a future G4 implementation
- **THEN** a stable task ID and meeting/source provenance are persisted with validated state, optional owner/date and no invented assignment

#### Scenario: Future approved task and regenerated minutes
- **WHEN** minutes are regenerated after a task has been approved
- **THEN** the approved task and its history remain intact and are never silently overwritten by the new draft
