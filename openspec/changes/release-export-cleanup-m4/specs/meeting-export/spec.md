# Spec Delta

## Purpose

Lets a user take a saved meeting transcript and reviewed minutes into ordinary external documents while retaining control over when and where content is copied.

## ADDED Requirements

### Requirement: Export the selected saved minutes version
The application SHALL export the minutes version currently selected in Meetings as a UTF-8 Markdown document named `minutes.md` by default. The document SHALL include the saved content, its review state, and human-readable source timestamps without API keys or internal file paths.

#### Scenario: Export approved minutes
- **WHEN** the user chooses Export minutes for a selected approved version and saves to a chosen path
- **THEN** the Markdown file opens outside fahmm with its Vietnamese text, approval state, and source timestamps intact

#### Scenario: Export unverified minutes
- **WHEN** the user exports a selected unverified version
- **THEN** the document visibly identifies it as unverified and does not claim approval

#### Scenario: No saved minutes version
- **WHEN** the user attempts to export minutes before a version exists
- **THEN** the application explains that a saved minutes version is required and creates no file

### Requirement: Export the selected saved transcript
The application SHALL export the working text of the transcript run currently selected in Meetings as a UTF-8 plain-text document named `transcript.txt` by default. Segment timestamps SHALL remain readable, and an earlier run SHALL remain selectable for export.

#### Scenario: Export edited transcript
- **WHEN** the user exports a selected run after saving transcript corrections
- **THEN** the text file contains that run's corrected segment text and timestamps rather than the original ASR text or another run

#### Scenario: No transcript run
- **WHEN** the selected meeting has no saved transcript run
- **THEN** transcript export is unavailable and no empty file is created

### Requirement: Require saved content before output
The application SHALL not silently export unsaved transcript or minutes editor text. It SHALL direct the user to save or discard pending edits before file export or clipboard copy.

#### Scenario: Pending minutes edit
- **WHEN** minutes text differs from the selected saved version and the user chooses Export or Copy Markdown
- **THEN** the application blocks the action, explains the pending edit, and leaves the selected saved version unchanged

#### Scenario: Pending transcript edit
- **WHEN** the transcript editor has unsaved changes and the user chooses Export transcript
- **THEN** the application blocks export until those changes are saved or discarded

### Requirement: Copy Markdown on explicit action
The application SHALL copy the same saved Markdown representation used by minutes export to the system clipboard only after the user chooses Copy Markdown. It SHALL not copy audio, transcripts, API keys, or internal paths as extra clipboard formats.

#### Scenario: Copy selected version
- **WHEN** the user chooses Copy Markdown for a saved minutes version
- **THEN** the clipboard contains that version's Markdown text and the UI confirms the copy

### Requirement: Preserve local data on export failure
The application SHALL write only to the user-selected destination, ask before overwriting an existing file, and leave the previous destination file and all meeting data intact if export fails. It SHALL disclose that a user-selected shared location or clipboard may be accessible to other applications.

#### Scenario: User declines overwrite
- **WHEN** the selected destination already exists and the user declines replacement
- **THEN** the existing file remains byte-for-byte unchanged and no meeting data changes

#### Scenario: Write fails
- **WHEN** the destination is unavailable or a write fails before completion
- **THEN** the application reports the error without leaving a partial target or altering meeting audio, transcript, or minutes

#### Scenario: Restricted meeting export
- **WHEN** a user explicitly exports a Restricted meeting to a chosen local path
- **THEN** the file is written locally without a provider request or automatic network call
