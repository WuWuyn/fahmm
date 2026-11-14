# Spec Delta

## Purpose

Defines a portable Windows release that users can launch without development tools and a verification record that distinguishes tested behavior from outstanding v1 acceptance.

## ADDED Requirements

### Requirement: Provide a standalone Windows portable package
The project SHALL produce a versioned Windows 10/11 x64 portable archive containing a launchable fahmm executable and its runtime dependencies. A user SHALL not need to install Python, a separate FFmpeg executable, an account, an API key, a server, or a GPU to launch the app and record locally.

#### Scenario: Fresh-machine launch
- **WHEN** a user extracts the archive on a clean supported Windows x64 machine without Python or FFmpeg installed
- **THEN** the app opens its four English screens and can create a local recording without a subscription or account

#### Scenario: No model is installed
- **WHEN** the portable app opens without an installed Whisper model
- **THEN** it remains usable for recording and import, explains how to install a compatible model, and does not download one automatically

### Requirement: Keep user data and secrets outside the package
The package SHALL contain no meeting recordings, transcripts, minutes, user API keys, or provider profiles. Runtime meeting data and protected keys SHALL remain in the user's local Windows profile rather than the extracted application directory.

#### Scenario: Archive inspection
- **WHEN** the release archive is inspected before distribution
- **THEN** it contains only application assets and approved notices, with no user meeting content or credentials

#### Scenario: Move the app folder
- **WHEN** the extracted app folder is moved after a meeting has been created
- **THEN** that meeting remains in the user's local data location and can be reopened by the moved app

### Requirement: Publish an integrity value and instructions
Each portable archive SHALL have a corresponding SHA-256 checksum and concise English instructions for extraction, launch, model installation, local-data location, export, deletion, and privacy modes. The instructions SHALL explain that first-use offline transcription requires a model installed beforehand.

#### Scenario: Verify package integrity
- **WHEN** a user hashes a downloaded archive and compares it with its published checksum
- **THEN** a matching archive is identifiable before extraction

### Requirement: Include reviewed third-party notices
The release SHALL include an inventory and required license/attribution notices for bundled runtime dependencies and any bundled model assets. A model whose redistribution terms have not been reviewed SHALL not be bundled.

#### Scenario: Review release contents
- **WHEN** the package is prepared for distribution
- **THEN** the release record identifies the bundled dependency/model versions and their reviewed license evidence, and the archive contains required notices

### Requirement: Preserve local-first behavior in the frozen app
Packaging SHALL not introduce automatic telemetry, content uploads, cloud fallback, model downloads, or provider connectivity probes. A previously installed local model SHALL support offline transcription and offline minutes generation in the packaged app without an API key.

#### Scenario: Offline end-to-end path
- **WHEN** a compatible model is already installed and network access is blocked
- **THEN** the packaged app can record or import, transcribe, draft minutes, export, and delete a test meeting without meeting-content egress

### Requirement: Record release acceptance honestly
The project SHALL run AT-11 and a packaged-app smoke/end-to-end matrix on supported Windows targets and SHALL publish a release verification record with pass, fail, or pending status for required v1 acceptance checks. It SHALL not label a build fully accepted v1 while required M1 real-meeting checks or other release gates remain pending.

#### Scenario: AT-11 passes
- **WHEN** a test meeting's Markdown and TXT exports open outside the app and confirmed deletion removes its owned data and temporary files
- **THEN** the release record marks AT-11 passed with reproducible evidence

#### Scenario: Real-meeting evidence unavailable
- **WHEN** a permitted 20-minute Teams/Meet recording and real-hardware recovery check have not been completed
- **THEN** the record keeps AT-01, AT-02, or AT-10 pending as applicable and does not claim full v1 acceptance

#### Scenario: Speech-quality coverage unavailable
- **WHEN** approved Northern, Southern, or Vietnamese-English speech samples are unavailable
- **THEN** each missing case remains explicitly pending instead of being reported as passed
