# Spec Delta

## Purpose

Audio import lets users create a local meeting from an existing recording without changing the original file or depending on a network service.

## ADDED Requirements

### Requirement: Import supported audio
The app SHALL accept user-selected WAV, MP3, M4A, and FLAC files whose audio can be decoded, and SHALL create one local meeting per successful import.

#### Scenario: Import a supported recording
- **WHEN** the user selects a valid WAV, MP3, M4A, or FLAC file and confirms import
- **THEN** the app creates a meeting with a playable local copy of the audio and identifies it as imported

#### Scenario: Unsupported format
- **WHEN** the user selects a file in an unsupported format
- **THEN** the app explains that the format is unsupported and does not create a completed meeting

### Requirement: Preserve the source file
The app MUST leave the selected source file unchanged and SHALL use the meeting's local copy for later processing.

#### Scenario: Source is moved after import
- **WHEN** a successfully imported source file is moved or deleted outside the app
- **THEN** the meeting's local audio remains available for playback and transcription

### Requirement: Handle failed imports safely
The app SHALL reject unreadable, corrupt, or incomplete audio with a clear English error and SHALL not present a partial copy as usable meeting audio.

#### Scenario: Decode or copy fails
- **WHEN** the selected file cannot be decoded or copying it fails
- **THEN** the app reports the failure, leaves the original file untouched, and offers a retry without a false successful meeting

### Requirement: Keep imports local and restricted
A new imported meeting MUST default to Internal/Restricted and MUST NOT upload its audio or metadata during import.

#### Scenario: Offline import
- **WHEN** the user imports supported audio without an internet connection or API key
- **THEN** the import succeeds locally and the meeting remains Internal/Restricted
