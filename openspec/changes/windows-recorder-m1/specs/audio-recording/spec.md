# Spec Delta

## Purpose

Allow Windows users to deliberately record meetings from system audio and microphone, see a clear status, and play back locally captured content.

## ADDED Requirements

### Requirement: Select two audio sources before recording
The app SHALL list available WASAPI speaker loopbacks and microphones and let the user select each source before starting.

#### Scenario: Available devices
- **WHEN** the user opens Recorder on Windows with an available speaker and microphone
- **THEN** the app shows both source choices and does not start capturing

#### Scenario: A source is missing
- **WHEN** the user tries to record but one selected source cannot be opened
- **THEN** the app identifies the failing source and does not claim that both sources are recording

### Requirement: Deliberate simultaneous capture
The app SHALL start WASAPI loopback and microphone capture only after the user presses Record; it MUST NOT use a meeting bot or send audio to a network service.

#### Scenario: Start recording
- **WHEN** the user presses Record and both sources open successfully
- **THEN** the app captures both sources locally and shows a recording indicator and elapsed time

#### Scenario: Before Record
- **WHEN** Recorder is idle
- **THEN** the app neither captures nor saves microphone or system audio

### Requirement: Pause, resume, and stop
The app SHALL support Pause/Resume/Stop; the displayed duration and output audio MUST exclude paused time.

#### Scenario: Pause and resume
- **WHEN** the user presses Pause and then Resume during a recording
- **THEN** the indicator changes accordingly and no audio captured during the pause is included

#### Scenario: Stop a session
- **WHEN** the user presses Stop
- **THEN** the app closes capture and creates a playback file containing saved system and microphone audio

### Requirement: Source-specific capture errors
The app SHALL retain saved audio and identify the affected source if a device disconnects or fails during recording.

#### Scenario: Device disappears mid-session
- **WHEN** one source stops providing data during recording
- **THEN** the app stops safely, retains captured data, and shows a source-specific error
