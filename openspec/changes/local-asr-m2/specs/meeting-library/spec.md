# Spec Delta

## Purpose

The meeting library makes local recorded and imported meetings discoverable and resumable across app restarts without an account or server.

## ADDED Requirements

### Requirement: List local meetings
The app SHALL list recorded and imported meetings by creation time, editable name, and current recording or transcription status, with newest first by default.

#### Scenario: Open Meetings
- **WHEN** the user opens Meetings after recording or importing audio
- **THEN** the meeting appears with its time, name, source, and status

#### Scenario: Rename a meeting
- **WHEN** the user changes a meeting name and saves it
- **THEN** the new name appears after app restart without changing the meeting audio

### Requirement: Reopen meeting data
The app SHALL reopen a saved meeting for local audio playback, transcript review, and transcription retry when those actions are available for its state.

#### Scenario: Reopen a recorded meeting
- **WHEN** the user opens a completed M1 recording from Meetings
- **THEN** its saved audio is available for playback and local transcription

#### Scenario: Reopen an imported meeting
- **WHEN** the user reopens a successfully imported meeting after restarting the app
- **THEN** its local audio and any saved transcript remain available

### Requirement: Preserve restricted classification
Every new meeting MUST default to Internal/Restricted, and existing M1 meetings with no classification SHALL be treated as Internal/Restricted when opened.

#### Scenario: Open legacy meeting
- **WHEN** the app opens a meeting created by M1 without a privacy field
- **THEN** it is treated as Internal/Restricted and no meeting content is sent externally

### Requirement: Provide English top-level navigation
The app SHALL expose Recorder, Meetings, Models, and Settings as its top-level screens with English labels; M2 SHALL not expose a cloud send action.

#### Scenario: Navigate between screens
- **WHEN** the user switches among Recorder, Meetings, Models, and Settings
- **THEN** the requested screen opens without losing saved recording or transcript data
