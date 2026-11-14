# Spec Delta

## Purpose

Lets a user remove one meeting's app-owned local content deliberately, without affecting other meetings, original imported files, models, or copies exported elsewhere.

## ADDED Requirements

### Requirement: Confirm the exact meeting before deletion
The application SHALL require an explicit confirmation that identifies the selected meeting and states that its app-owned audio, transcript runs, minutes versions, metadata, and temporary files will be removed. Canceling SHALL make no changes.

#### Scenario: Confirm selected meeting
- **WHEN** the user selects a meeting, chooses Delete meeting, and confirms its identified name
- **THEN** the application removes that meeting's app-owned content and removes it from the Meetings list

#### Scenario: Cancel deletion
- **WHEN** the user closes or declines the deletion confirmation
- **THEN** the meeting and all of its files remain unchanged

### Requirement: Refuse deletion during active work
The application SHALL refuse or defer deletion while the selected meeting is recording, being recovered, imported, transcribed, generating minutes, sending to a provider, or otherwise writing its data. It SHALL stop playback of that meeting before deletion and SHALL prevent a new job from starting between the final eligibility check and deletion.

#### Scenario: Active transcription
- **WHEN** a transcription job is active for the selected meeting and the user requests deletion
- **THEN** the application explains why deletion is unavailable and preserves the meeting until the job ends or is canceled

#### Scenario: Active provider send
- **WHEN** a confirmed provider request for the selected meeting is in progress
- **THEN** deletion cannot race the request or remove files before it finishes

### Requirement: Limit deletion to app-owned paths
Deletion SHALL be confined to the validated selected meeting directory and its associated app-owned temporary staging paths. It SHALL not follow links or reparse points outside that scope, and SHALL not remove any other meeting, managed model, provider profile, external original import, chosen export, or system clipboard content.

#### Scenario: Imported original remains
- **WHEN** the user deletes a meeting created from an external audio file
- **THEN** fahmm's stored copy and meeting data are removed while the original file at its import location remains unchanged

#### Scenario: Separate export remains
- **WHEN** a meeting with a previously exported Markdown file is deleted
- **THEN** the selected meeting disappears but the separately exported document remains at the location the user chose

#### Scenario: Link escapes meeting folder
- **WHEN** a meeting directory or one of its descendants contains a link or reparse point to another location
- **THEN** deletion rejects or safely unlinks that entry without traversing and deleting the outside target

### Requirement: Report incomplete deletion accurately
The application SHALL report success only after the selected app-owned content and associated temporary files are gone. If a filesystem error interrupts deletion, it SHALL report the remaining data and provide a safe retry path without affecting other meetings.

#### Scenario: Access denied midway
- **WHEN** Windows denies removal of a selected meeting file
- **THEN** the application reports incomplete deletion and leaves unrelated meetings and models intact

### Requirement: Explain deletion limits
The confirmation SHALL explain that ordinary deletion is not secure erasure and cannot remove copies the user exported, placed on the clipboard, or stored in system backups.

#### Scenario: User reviews scope
- **WHEN** the confirmation dialog opens
- **THEN** the user sees the deletion scope and limits before choosing Confirm or Cancel

### Requirement: Handle abandoned temporary imports
The application SHALL identify abandoned app-owned import staging directories that no active import owns and offer an explicit cleanup action. Cleanup SHALL not remove a completed meeting or an unrelated path.

#### Scenario: Interrupted import leaves staging
- **WHEN** an import was interrupted and its staging directory remains after restart
- **THEN** the app can identify and remove that orphan only after user confirmation
