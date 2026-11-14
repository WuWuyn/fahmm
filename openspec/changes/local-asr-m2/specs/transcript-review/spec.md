# Spec Delta

## Purpose

Transcript review lets users correct recognized speech against timestamped source audio while preserving what the recognition model originally produced.

## ADDED Requirements

### Requirement: Store reviewable transcript segments
For each completed transcription run, the app SHALL persist timestamped original segments, the model identity and revision, language settings, and an editable working copy in the meeting folder.

#### Scenario: Open a completed run
- **WHEN** the user opens a meeting with a completed transcription
- **THEN** the app shows its timestamped segments and the model and language used

### Requirement: Edit transcript text
The app SHALL let the user edit segment text and save those edits locally without altering the original recognized text or its source timestamps.

#### Scenario: Correct a segment
- **WHEN** the user changes and saves a segment's text
- **THEN** the working transcript shows the correction after reopening while the original recognized text remains available

#### Scenario: Save fails
- **WHEN** a transcript edit cannot be saved
- **THEN** the app reports the failure and does not claim the edit was persisted

### Requirement: Preserve prior work on rerun
A new transcription run MUST NOT overwrite or delete prior completed runs or their saved edits. The user SHALL be able to choose which completed run is active for review.

#### Scenario: Rerun with another model
- **WHEN** the user starts and completes a new run using another installed model
- **THEN** the new result is available alongside prior runs and prior edits remain accessible

#### Scenario: Rerun fails or is cancelled
- **WHEN** a new run fails or is cancelled
- **THEN** the previously active completed transcript and its edits remain available
