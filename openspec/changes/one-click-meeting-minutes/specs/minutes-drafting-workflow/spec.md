# Spec Delta

## Purpose

Enable a user to create, inspect, edit, regenerate, and export a universal source-linked meeting-minutes draft from an existing saved transcript with one primary action and no required setup.

## ADDED Requirements

### Requirement: One-action draft creation
The system SHALL offer a primary Generate meeting minutes action for a meeting with a saved, usable active transcript. One activation SHALL create and immediately display a new unverified minutes version without requiring a meeting type, prompt, template, provider, or copied transcript.

#### Scenario: Saved transcript generates minutes
- **GIVEN** a meeting has a saved active transcript containing speech
- **WHEN** the user activates Generate meeting minutes
- **THEN** a new source-linked draft is saved and displayed in the current meeting

#### Scenario: Missing transcript
- **GIVEN** a meeting has no saved active transcript
- **WHEN** the user opens its minutes panel
- **THEN** the generation action is unavailable with an explanation to transcribe first, and no minutes version is created

#### Scenario: Empty transcript
- **GIVEN** the active transcript has no usable nonblank speech
- **WHEN** the user opens its minutes panel or requests generation
- **THEN** the action is unavailable or returns a clear error without changing saved versions

#### Scenario: Generation in progress
- **WHEN** the user activates generation
- **THEN** the interface shows a working state and prevents a duplicate request until completion or failure

### Requirement: Universal, conservative structure
The generated draft SHALL use one common structure with meeting information, executive summary, discussion points, requirements, decisions, proposed solutions, action suggestions, open questions, risks and blockers, and next steps. It MUST preserve unknown facts and distinguish a proposal from a confirmed decision.

#### Scenario: Partial meeting evidence
- **GIVEN** a transcript lacks participants, customer, owner, deadline, or a decision
- **WHEN** a draft is generated
- **THEN** the corresponding field or section stays empty or explicitly unknown, and no person, date, or decision is fabricated

#### Scenario: Proposed solution without agreement
- **GIVEN** a transcript proposes a solution but does not record agreement
- **WHEN** a draft is generated
- **THEN** the proposal is not classified as a confirmed decision

#### Scenario: Requirements and technical terms
- **GIVEN** a Vietnamese transcript contains an explicit requirement and English API, database, or system names
- **WHEN** a draft is generated
- **THEN** those terms remain in cited discussion or requirement text without translation that changes their meaning

#### Scenario: Empty applicable section
- **GIVEN** there is no transcript evidence for one common section
- **WHEN** the user reviews the draft
- **THEN** the section remains visible and editable without a fabricated entry

### Requirement: Evidence and coverage
Generated material claims SHALL cite real segments from the selected transcript run with timestamps and saved text. The draft SHALL cover a long meeting across its time span without sending content externally, duplicating the same claim within a section, or silently truncating to the opening minutes.

#### Scenario: Review a generated claim
- **WHEN** the user opens a claim's source reference
- **THEN** the cited transcript segment and its corresponding audio time can be opened

#### Scenario: Long transcript
- **GIVEN** a transcript spans one hour with topics in its beginning, middle, and end
- **WHEN** a draft is generated
- **THEN** the discussion includes cited coverage from all three periods within bounded output limits

#### Scenario: Edited transcript
- **GIVEN** the active run has saved text corrections
- **WHEN** a draft is generated
- **THEN** claims and source excerpts use the saved working text while the original ASR output remains intact

### Requirement: Safe local persistence and regeneration
Generation SHALL use the existing atomic, versioned minutes store. A failure MUST preserve all saved minutes and transcript data. Regeneration MUST create a new version and warn before discarding unsaved edits; it MUST NOT replace an earlier approved or edited version.

#### Scenario: Generation failure
- **GIVEN** a minutes version already exists
- **WHEN** generation fails before a new version is committed
- **THEN** the earlier version remains readable and the interface offers retry

#### Scenario: Regenerate after edits
- **GIVEN** the displayed minutes contain unsaved edits
- **WHEN** the user requests another draft
- **THEN** the interface asks whether to discard those unsaved edits before creating a separate version

#### Scenario: Regenerate after approval
- **GIVEN** an approved version exists
- **WHEN** the user generates again
- **THEN** a new unverified version is selected and the approved version remains unchanged and selectable

#### Scenario: Save and reopen
- **WHEN** the user edits and saves the draft, then reopens the meeting
- **THEN** the edited version, review state, and source references remain available

### Requirement: Existing export and provider boundaries
The universal draft SHALL render and export from its saved version. Restricted one-click generation MUST remain local and visibly identify its extractive nature. Existing optional provider generation SHALL retain explicit payload preview and per-send authorization, and malformed provider output MUST NOT overwrite saved minutes.

#### Scenario: Export the current draft
- **WHEN** the user exports the selected universal version as Markdown
- **THEN** the exported structure, text, certainty labels, and source references match that saved version

#### Scenario: Restricted meeting
- **GIVEN** a Restricted meeting and no network connection or provider profile
- **WHEN** the user creates a one-click draft
- **THEN** generation succeeds locally and no meeting content is sent to an external endpoint

#### Scenario: Provider returns invalid JSON
- **GIVEN** a user separately authorizes an optional provider request
- **WHEN** that provider returns malformed or unsupported structured output
- **THEN** the request fails safely or yields only valid cited candidates, and previous saved minutes remain intact
