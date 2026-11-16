# Spec Delta

## Purpose

Accept the actual Record/Import → offline transcription → review → source playback flow on Windows, beyond controlled component tests.

## ADDED Requirements

### Requirement: Explicit dual-source recording and truthful state
On Windows 10/11 x64, the app SHALL capture selected WASAPI system loopback and microphone sources locally only after deliberate Record. It SHALL expose source-specific errors instead of reporting two-source success if either source fails. A live end-to-end acceptance test SHALL verify both sources contain intelligible relevant speech, not merely nonzero samples.

#### Scenario: Permitted live meeting
- **WHEN** the tester records a permitted 20-minute Teams/Meet meeting with headphones, a selected system output and microphone
- **THEN** no meeting bot is added, the saved file has independently audible remote and local speech, and the test report names devices, duration and listener observations

#### Scenario: Selected device is missing
- **WHEN** the app cannot open a selected loopback or microphone
- **THEN** it identifies the failing source and never displays a misleading state that both sources are recording

#### Scenario: Before Record
- **WHEN** the app is idle with devices selected
- **THEN** no microphone or system stream is captured or transmitted

### Requirement: Pause/resume/stop preserve real audio timing
The app SHALL exclude paused time from saved audio and displayed capture duration, SHALL create a valid completed local recording on Stop, and SHALL make controls and status accurately reflect the operation.

#### Scenario: Real-device pause and resume
- **WHEN** the tester pauses and resumes a live meeting recording for a measurable interval
- **THEN** audio from the paused interval is absent and the final duration and UI indicator reflect active capture time

#### Scenario: Stop and replay
- **WHEN** the tester stops a recording
- **THEN** saved playback opens and both expected channels can be listened to after reopening the meeting

### Requirement: Crash recovery without collateral damage
The app SHALL recover previously committed recording chunks after unexpected termination, report missing/uncommitted data honestly and preserve other meetings.

#### Scenario: Interrupted live recording
- **WHEN** the tester terminates the desktop application after at least one committed chunk and reopens it
- **THEN** the incomplete session can be recovered, the recovered audio is listenable, and an unrelated saved meeting is unchanged

### Requirement: Common audio import and safe failure
The app SHALL import WAV, MP3, M4A and FLAC without enabling capture or requiring cloud service, and SHALL leave existing meeting data unaffected by Cancel or unsupported input.

#### Scenario: Unsupported file or cancelled dialog
- **WHEN** the user cancels a native import dialog or selects an unsupported file
- **THEN** the app does not create a false completed recording, corrupt an existing meeting or expose an unmanaged file path to the webview

### Requirement: Offline Vietnamese transcription with actionable progress
Using a previously installed compatible faster-whisper/CTranslate2 model, the app SHALL transcribe saved audio locally, produce timestamped segments, allow Cancel/Retry and preserve prior saved results when a job fails. No API key or network shall be needed after model installation.

#### Scenario: 30-minute Vietnamese recording
- **WHEN** the tester imports a licensed 30-minute Vietnamese sample and starts recognition with outbound networking blocked
- **THEN** the transcript has timestamp coverage through the recording, the UI remains responsive and there are zero content-network attempts

#### Scenario: Failed recognition job
- **WHEN** an ASR worker crashes or is cancelled
- **THEN** the app reports the failure, allows a safe retry and retains any previous completed transcript run

### Requirement: Selected-recording transcription range and source timestamps
The app SHALL transcribe the selected meeting's saved audio from a user-selected time, or 00:00 by default, through the end. Segment timestamps SHALL refer to the original recording and stay within its duration. Retry SHALL retain the meeting and start time.

#### Scenario: User selects a playback position before transcription
- **WHEN** the user selects a meeting, seeks its player to a start time and requests transcription from that position
- **THEN** only that meeting's saved audio from the chosen time through its end is processed; the run retains the chosen start time and its transcript timestamps seek to the original recording

#### Scenario: Default and invalid start times
- **WHEN** the user leaves the start time unset or provides a time at or beyond the end of the recording
- **THEN** an unset time starts at 00:00; an out-of-range time is rejected without replacing a prior transcript run

### Requirement: Model provenance and optional download
Models SHALL only download on user request, SHALL reject incompatible custom repositories and SHALL support offline cached reuse and safe deletion of non-active models.

#### Scenario: Cache reuse after installation
- **WHEN** a model has been explicitly installed and the app is offline
- **THEN** selection and transcription continue using cached weights without a new download

### Requirement: Transcript edit source and seek continuity
The app SHALL retain original ASR content separately from editable working text and persist edits when a meeting is reopened. Transcript and minutes citations SHALL resolve to valid source segments and permit local playback from their timestamps.

#### Scenario: Edit a timestamped segment
- **WHEN** a user corrects a segment, saves it and reopens the meeting
- **THEN** the edited working text persists, original output remains intact and the cited timestamp still seeks the same audio

#### Scenario: Scope a playback ticket
- **WHEN** an expired ticket or a ticket from another meeting is used
- **THEN** the native media handler denies access without revealing arbitrary local files

### Requirement: Speech quality evidence is representative
Before claiming broad Vietnamese accuracy, the project SHALL document a reproducible test set covering Northern speech, Southern speech and Vietnamese mixed with English, including sample provenance, word/character error measurements or annotated error analysis. Numeric thresholds require explicit product approval and MUST NOT be inferred from a single controlled sample.

#### Scenario: Existing controlled sample only
- **WHEN** a 30-minute controlled sample passed but no regional/code-switching evaluation exists
- **THEN** the app MAY claim tested offline transcription and MUST NOT claim comprehensive regional-language accuracy
