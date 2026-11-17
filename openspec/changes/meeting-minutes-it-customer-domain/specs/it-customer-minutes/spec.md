# Spec Delta

## Purpose

Provide reviewable, evidence-linked meeting minutes for customer-facing IT and software engineering discussions while distinguishing confirmed facts, proposals, uncertainty, and action suggestions.

## ADDED Requirements

### Requirement: ITM-01 Select a meeting type and identify the meeting
The system SHALL let the user select `general`, `requirement_gathering`, `technical_discussion`, `project_status`, `issue_incident`, or `uat_feedback`. It SHALL retain title, meeting date/time, project/customer, participants, and objective as separate metadata fields. A recording or import timestamp SHALL NOT be presented as the actual meeting time without user confirmation; missing fields SHALL remain explicit.

#### Scenario: Existing meeting has no domain metadata
- **GIVEN** a saved meeting with no selected domain type or customer metadata
- **WHEN** the user opens its minutes workflow
- **THEN** the type is `general`, the saved title and recording/import timestamp remain available, and the unconfirmed meeting date/time, project/customer, participants, and objective are shown as unknown without changing the saved meeting

#### Scenario: User identifies a customer meeting
- **WHEN** the user selects `technical_discussion` and enters a project/customer and objective
- **THEN** the saved minutes version retains those values as user-provided metadata and labels them as such

### Requirement: ITM-02 Use one structured minutes schema
The system SHALL offer summary, discussion topics, requirements, decisions, proposed solutions, open questions, risks/blockers, proposed action items, next steps, and evidence references in one versioned structure. Empty sections SHALL remain absent or visibly empty rather than acquire generated filler.

#### Scenario: Meeting has only topics and questions
- **WHEN** a reviewed transcript contains discussion and open questions but no supported decision or requirement
- **THEN** the draft contains cited topics and questions, and does not invent a decision or requirement

### Requirement: ITM-03 Distinguish requirement kinds and formality
Requirement entries SHALL distinguish business, functional, non-functional, business-rule, constraint, assumption, and change candidates. A discussed idea SHALL remain a candidate until the user confirms its classification and formal status; a transcript mention alone SHALL NOT become an approved customer requirement.

#### Scenario: Requirement gathering contains a constraint and an assumption
- **WHEN** a transcript explicitly states a deployment constraint and separately assumes a customer network property
- **THEN** the draft presents two source-linked candidates with distinct kinds and leaves the assumption unconfirmed

#### Scenario: Technical suggestion sounds like a requirement
- **WHEN** a participant says an API could use a particular protocol without agreeing that it must
- **THEN** the item is a proposed solution or open question, not a confirmed functional requirement

### Requirement: ITM-04 Separate decisions from proposed solutions
The system SHALL place only explicitly agreed, source-supported outcomes in decision candidates and SHALL keep unapproved approaches in proposed solutions. Generated entries SHALL require human review before a version is approved; version approval SHALL NOT imply customer sign-off.

#### Scenario: Architecture alternatives are discussed
- **WHEN** two database options are evaluated and the participants agree on neither
- **THEN** both remain proposals or discussion points and the decisions section has no fabricated choice

#### Scenario: Decision is explicit
- **WHEN** a cited segment records an explicit agreed architecture choice
- **THEN** the draft presents it as a decision candidate with its source and review state

### Requirement: ITM-05 Preserve project status and incident certainty
Project-status minutes SHALL distinguish progress, milestones, issues, blockers, risks, dependencies, and next steps. Incident minutes SHALL distinguish impact, findings, suspected cause, confirmed cause, workaround, resolution proposal, and follow-up; a suspected cause MUST NOT be displayed as confirmed.

#### Scenario: Status meeting reports a blocker
- **WHEN** a cited update says a milestone is delayed by an external dependency
- **THEN** the draft retains the milestone update and dependency/blocker relationship without inventing a recovery date

#### Scenario: Incident cause remains suspected
- **WHEN** the transcript says a database timeout might be the cause but investigation is ongoing
- **THEN** the cause is marked suspected or unresolved and no confirmed root cause is shown

### Requirement: ITM-06 Keep UAT observations separate from acceptance
UAT/customer-feedback minutes SHALL distinguish test scenario, observed result, customer feedback, reported defect, change request, and pending confirmation. The system MUST NOT label an observation as customer acceptance unless explicit evidence and user confirmation support that label.

#### Scenario: Customer reports a defect during UAT
- **WHEN** a customer describes a failed test and asks for a change
- **THEN** the draft records the scenario, observation, defect, and change request as separate cited candidates without marking the test accepted

### Requirement: ITM-07 Keep proposed actions unassigned until reviewed
Each proposed action SHALL retain description, optional proposed owner, optional proposed deadline, source reference, and confirmation state. Missing owner/deadline SHALL be `Chưa rõ`; minutes actions SHALL remain suggestions and SHALL NOT become independently tracked tasks through generation or version approval.

#### Scenario: Follow-up has no owner or deadline
- **WHEN** the transcript names a follow-up but no person or date
- **THEN** the draft cites the source, shows `Chưa rõ` for both fields, and labels the action as a suggestion

### Requirement: ITM-08 Preserve claim-level evidence and uncertainty
Each generated material claim SHALL retain its transcript run, segment ID, source timestamp, and the excerpt used when drafted. An invalid, missing, or changed source SHALL be visibly flagged for review; a source ID alone SHALL NOT be treated as proof that the claim is true. User-provided content without transcript evidence SHALL be labeled as user-provided.

#### Scenario: Open a cited claim
- **WHEN** the reviewer selects a claim's source
- **THEN** the corresponding saved transcript segment opens and playback seeks to its timestamp

#### Scenario: Transcript text changes after drafting
- **WHEN** the cited working transcript segment is edited after a minutes version was saved
- **THEN** that version retains the excerpt used at creation and indicates that the current source differs before the claim can be reconfirmed

#### Scenario: Provider returns an unsupported citation
- **WHEN** a provider claim cites a segment outside the reviewed selection
- **THEN** the claim is rejected or marked unsupported and cannot appear as a confirmed fact

### Requirement: ITM-09 Generate conservatively in either privacy mode
Restricted generation SHALL remain local and extractive without a required account, key, network, GPU, or local LLM. Provider generation SHALL use only the existing Cloud permitted preview/confirmation boundary and reviewed selected transcript; both paths SHALL preserve Vietnamese output headings and English technical terms.

#### Scenario: Restricted offline draft
- **GIVEN** a Restricted meeting with a reviewed transcript and blocked network access
- **WHEN** the user creates IT/SE minutes
- **THEN** an unverified, source-linked extractive draft is saved locally without content egress or a claim of semantic AI summarization

#### Scenario: Provider draft
- **WHEN** the user confirms the exact selected transcript and destination for a Cloud permitted meeting
- **THEN** a provider draft may be saved as unverified, with unsupported claims and missing fields requiring review

### Requirement: ITM-10 Preserve reviewed versions and truthful export
Editing, changing meeting type, or regenerating SHALL save a new unverified minutes version without overwriting an approved version. Export SHALL show review state, draft origin, action-suggestion status, and claim-level sources for structured content. Freeform edited text SHALL NOT inherit claim-level verification automatically.

#### Scenario: Regenerate after approval
- **WHEN** the user approves one version and creates a new domain-specific draft
- **THEN** the approved version remains byte-for-byte available and the new version is unverified

#### Scenario: Export a freeform edit
- **WHEN** the user exports a version whose freeform Markdown differs from its structured source-linked draft
- **THEN** the export labels the edited text as not automatically source-verified, keeps underlying source references distinguishable, and does not imply those references verify every edited sentence

### Requirement: ITM-11 Read older minutes without eager migration
The system SHALL continue to read, select, approve, and export pre-domain minutes versions. Creating a new structured version SHALL NOT rewrite older minutes, original ASR output, working transcript, recording, or another meeting.

#### Scenario: Existing M3 minutes are reopened
- **WHEN** a meeting contains only an older generic minutes version
- **THEN** that version remains readable and exportable, and the new domain structure is used only for a newly created version

#### Scenario: New version save fails
- **WHEN** saving a domain-specific draft fails before commit
- **THEN** the prior approved minutes, transcript, and audio remain readable and unchanged
