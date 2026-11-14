# Spec Delta

## Purpose

Turn a reviewed local transcript into usable Vietnamese meeting minutes while preserving the source evidence and the user's control over every draft and approved version.

## ADDED Requirements

### Requirement: Offline extractive draft
The system SHALL create a local, source-linked extractive minutes draft from the selected transcription run's current edited text without an account, API key, network connection, GPU, or local LLM. It SHALL identify the result as an unverified extractive draft rather than a complete semantic AI summary.

#### Scenario: Restricted meeting without internet
- **WHEN** a user requests an offline draft for a Restricted meeting with a reviewed transcript while the network is unavailable
- **THEN** the app creates the draft locally without sending meeting content or requiring provider configuration

#### Scenario: No transcript is available
- **WHEN** a user requests minutes for a meeting with no completed transcription run or no usable text
- **THEN** the app explains that a transcript is needed and leaves existing meeting data unchanged

### Requirement: Vietnamese structure and unknown facts
The default minutes SHALL use Vietnamese headings for title/date, summary, topics, decisions, action items, open questions, and source references. The system MUST use an explicit Vietnamese unknown marker for unsupported fields and MUST NOT infer attendees, owners, due dates, decisions, or commitments without transcript evidence.

#### Scenario: Owner and due date absent
- **WHEN** the transcript contains a task but names no owner or deadline
- **THEN** the action item displays `Chưa rõ` for those fields and cites the source segment

#### Scenario: No supported decision
- **WHEN** no transcript segment supports an agreed decision
- **THEN** the decisions section says the decision is unknown instead of inventing one

### Requirement: Source-linked review
Every extracted topic, decision, action, and important conclusion SHALL retain a reference to one or more transcript segments and their timestamps. The user SHALL be able to open the cited segment and play its source audio from the minutes review screen.

#### Scenario: Review a draft claim
- **WHEN** the user selects a source citation in the minutes draft
- **THEN** the linked transcript segment opens and playback can start at its timestamp

### Requirement: Local version review and approval
The system SHALL save minutes drafts and user edits locally per meeting, distinguish unverified and approved versions, and preserve an approved version when the user edits or regenerates another draft. Regeneration SHALL use the selected transcript run and SHALL NOT silently replace prior minutes.

#### Scenario: Regenerate after approval
- **WHEN** the user regenerates minutes after approving an earlier version
- **THEN** a new unverified version is created and the approved version remains available unchanged

#### Scenario: Edit and reopen
- **WHEN** the user edits a draft and reopens the meeting
- **THEN** the edited content, its review state, and its source links are available for further review

### Requirement: Editable minutes guidance
The user SHALL be able to review and edit the minutes template or generation guidance before creating a new version, with a Vietnamese default available. A changed template SHALL affect only subsequent generations.

#### Scenario: Change the template
- **WHEN** the user changes the template and regenerates minutes
- **THEN** the new version uses that template and earlier versions retain their saved content
