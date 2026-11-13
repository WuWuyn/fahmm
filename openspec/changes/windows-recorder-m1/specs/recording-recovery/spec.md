# Spec Delta

## Purpose

Protect locally captured audio from app crashes or power loss by committing finished chunks and allowing users to recover unfinished sessions.

## ADDED Requirements

### Requirement: Store each meeting separately
The app SHALL create a separate local directory for each meeting and store both source streams plus state metadata without overwriting a previous meeting.

#### Scenario: New session
- **WHEN** the user starts a new recording
- **THEN** the app creates a uniquely identified directory, writes metadata, and stores system/microphone audio separately

### Requirement: Persist periodically while recording
The app SHALL finish and flush short audio chunks during capture so a crash loses at most the unflushed portion.

#### Scenario: Unexpected termination
- **WHEN** the process terminates after at least one chunk was committed
- **THEN** the flushed chunks remain readable and the session is identified as unfinished on restart

### Requirement: Recover an unfinished session
The app SHALL let the user create a playback file from saved chunks of an unfinished meeting without inventing content.

#### Scenario: Reopen after a crash
- **WHEN** the user reopens the app after a recording was interrupted
- **THEN** the app shows the recoverable meeting and offers to generate a playback file from saved data

#### Scenario: Corrupt audio chunk
- **WHEN** one chunk of an unfinished meeting cannot be read
- **THEN** the app keeps readable chunks, reports the recovery limit, and does not modify another meeting

### Requirement: Consistent session completion
The app SHALL mark a session complete only after its playback file is created successfully; a failed session MUST remain recoverable.

#### Scenario: Normal completion
- **WHEN** the user presses Stop and the playback file is written successfully
- **THEN** metadata marks the session complete and the app shows the file path

#### Scenario: Final file failure
- **WHEN** playback-file creation fails
- **THEN** metadata remains incomplete and source chunks remain available for a later recovery attempt
