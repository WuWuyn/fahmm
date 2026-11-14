# Spec Delta

## Purpose

Defines the observable desktop workflows and status cues that must remain available when fahmm moves from its current interface to the new desktop interface.

## ADDED Requirements

### Requirement: Four-area desktop navigation
The desktop application SHALL expose Recorder, Meetings, Models, and Settings as its four top-level areas and SHALL reopen existing local meetings without requiring an account or remote service.

#### Scenario: Open an existing meeting offline
- **WHEN** a user launches fahmm without network access and selects a saved meeting from Meetings
- **THEN** the application opens its locally saved details and available transcript and minutes versions

### Requirement: Recorder state is explicit
The Recorder SHALL let the user select system audio and microphone devices, start, pause, resume, and stop a recording, and see the current recording state and elapsed duration. Capture SHALL begin only after an explicit Record action.

#### Scenario: Recording changes state
- **WHEN** a user starts a recording with available devices and then pauses it
- **THEN** the application visibly distinguishes recording from paused state and preserves the captured audio for stopping or recovery

#### Scenario: Interrupted recording is recoverable
- **WHEN** fahmm restarts after an interrupted recording with committed chunks
- **THEN** the user can find and request recovery of that recording without altering another meeting

### Requirement: Meeting processing remains reviewable
Meetings SHALL support audio import, local transcription with visible progress and cancel/retry, timestamped transcript playback and editing, and selection of saved transcript and minutes versions.

#### Scenario: Review a completed transcription
- **WHEN** local transcription completes for a saved recording
- **THEN** the user can inspect timestamped segments, play their source audio, edit and save the working transcript, and retain the original recognition result

#### Scenario: Processing fails
- **WHEN** a transcription or minutes job fails or is canceled
- **THEN** the application reports a recoverable state and keeps previously saved audio, transcript, and minutes versions available

### Requirement: Local and cloud minutes remain distinct
The application SHALL label offline extractive minutes as unverified and source linked. For a Cloud permitted meeting, it SHALL show the destination and exact selected outgoing content and require confirmation for every provider send.

#### Scenario: Create a restricted offline draft
- **WHEN** a user creates minutes for a Restricted meeting
- **THEN** the application offers an unverified offline extractive draft with source references and sends no meeting content externally

#### Scenario: Review a cloud request
- **WHEN** a user requests provider minutes for a Cloud permitted meeting
- **THEN** the application shows the destination and outgoing request before a separate Confirm or Cancel decision, and Cancel sends nothing

### Requirement: Privacy state is visible without changing policy
The application SHALL display each meeting's persisted privacy classification using a legible local-only or cloud-permitted indicator. The indicator SHALL reflect backend state and SHALL NOT itself authorize a send.

#### Scenario: Newly created meeting
- **WHEN** the user opens a newly created meeting
- **THEN** the meeting is shown as local-only or restricted until the user explicitly changes its classification

### Requirement: Models and provider settings remain usable
Models SHALL show installed and downloadable compatible models, with explicit download progress and deletion of unused installations. Settings SHALL manage optional provider profiles without displaying stored API keys.

#### Scenario: Use an installed model offline
- **WHEN** the user selects an already installed model while offline
- **THEN** the model can be used for local transcription without a download or API key

### Requirement: Saved-output actions remain deliberate
The application SHALL export saved minutes and transcripts, and copy saved minutes Markdown, only after an explicit user action. Pending editor changes SHALL be saved or discarded before output; failure SHALL leave the saved version intact.

#### Scenario: Export with unsaved edits
- **WHEN** the user tries to export while the selected transcript or minutes editor has unsaved changes
- **THEN** the application requires the user to save or discard those changes before exporting a saved version

### Requirement: Desktop appearance supports task state
The application SHALL default to dark mode, offer light mode, keep navigation collapsible, and make recording and privacy state identifiable without relying on color alone.

#### Scenario: Recording in either theme
- **WHEN** the user switches theme while a recording is active
- **THEN** recording state and the active meeting's privacy classification remain legible and textually identifiable
