# Spec Delta

## Purpose

Local transcription turns saved meeting audio into a timestamped transcript on an ordinary Windows computer, including when no network or API key is available.

## ADDED Requirements

### Requirement: Transcribe saved audio locally
The app SHALL transcribe a saved recording or imported audio using only an installed local model and MUST NOT send meeting content to a network endpoint or fall back to cloud recognition.

#### Scenario: Offline transcription
- **WHEN** the user starts transcription with a compatible model already installed while the network is unavailable
- **THEN** the app produces a local transcript without an account, API key, server, or GPU

#### Scenario: No installed model
- **WHEN** the user requests transcription and no compatible local model is available
- **THEN** the app explains that a model must be installed and does not attempt a meeting-content network request

### Requirement: Language selection
The app SHALL default transcription language to Vietnamese (`vi`) and SHALL offer Auto Detect and English as explicit alternatives.

#### Scenario: Default language
- **WHEN** a user opens transcription options for a meeting without changing the language
- **THEN** Vietnamese is selected

#### Scenario: Alternative language
- **WHEN** the user selects Auto Detect or English before a run
- **THEN** the run uses that selection and records the selected and detected language when available

### Requirement: Timestamped segments
The app SHALL retain start and end times for each recognized segment in recording time and SHALL preserve Vietnamese text that contains English terms without imposing an English-only model.

#### Scenario: Mixed-language speech
- **WHEN** a compatible multilingual model transcribes Vietnamese speech containing English terms
- **THEN** the app displays the resulting text with segment timestamps for review

### Requirement: Responsive processing controls
The app SHALL show a processing state and available progress, keep the UI responsive, and provide Cancel and Retry controls without deleting saved audio or prior transcripts.

#### Scenario: Cancel a run
- **WHEN** the user cancels an active transcription
- **THEN** processing stops, the run is marked cancelled, and saved meeting data remains available

#### Scenario: Failed run
- **WHEN** decoding, model loading, or recognition fails
- **THEN** the app shows a clear English error and lets the user retry after addressing the cause

#### Scenario: Long recording
- **WHEN** the user transcribes a 30- to 60-minute Vietnamese recording
- **THEN** the UI remains responsive and reports that processing is ongoing until completion or failure
