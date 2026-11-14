# Spec Delta

## Purpose

Whisper model management makes compatible speech recognition models available locally through an explicit, inspectable download and cache workflow.

## ADDED Requirements

### Requirement: Show compatible model choices
The app SHALL present compatible multilingual Whisper base, small, medium, and large-v3-turbo choices where available, with publisher, license, estimated download size, and a resource warning for large choices.

#### Scenario: Browse recommendations
- **WHEN** the user opens Models
- **THEN** the app identifies installed models and shows the available recommendations and their publisher, license, estimated size, and suitability warning

### Requirement: Download models only on request
The app MUST contact Hugging Face for model files only after an explicit user download action and MUST NOT include meeting audio, transcripts, minutes, or meeting metadata in model requests.

#### Scenario: User starts a download
- **WHEN** the user selects a model and starts its download
- **THEN** the app shows progress and stores the model locally without attaching meeting content to requests

#### Scenario: No download requested
- **WHEN** the app starts or a meeting is transcribed without a download action
- **THEN** the app does not fetch model weights or metadata from Hugging Face

### Requirement: Validate compatible files
The app MUST load only local, complete, compatible CTranslate2 Whisper model assets and MUST NOT run repository code or enable remote-code trust.

#### Scenario: Custom compatible repository
- **WHEN** the user supplies a repository ID for a compatible CTranslate2 Whisper model and downloads it
- **THEN** the app validates the local assets before offering that model for transcription

#### Scenario: Incompatible repository
- **WHEN** a selected repository is not a compatible CTranslate2 Whisper model or lacks required assets
- **THEN** the app rejects it with an explanation and does not attempt to transcribe with it

### Requirement: Reuse and remove cached models
The app SHALL allow users to select installed models offline and delete an unused installed model without deleting meeting data or a model in active use.

#### Scenario: Select a cached model offline
- **WHEN** a previously downloaded compatible model is selected with no network access
- **THEN** it remains available for transcription with no network request

#### Scenario: Delete an unused model
- **WHEN** the user confirms deletion of an installed model that is not in active use
- **THEN** its managed local files are removed and meeting audio and transcripts remain intact

### Requirement: Recover from interrupted downloads
The app SHALL check available disk space before downloading, identify the downloaded revision, and offer a safe retry or resume after an interrupted transfer.

#### Scenario: Insufficient disk space
- **WHEN** the available space is insufficient for the estimated model download and working files
- **THEN** the app warns the user and does not begin the transfer

#### Scenario: Interrupted download
- **WHEN** a download fails or is interrupted
- **THEN** the model is not offered as installed and the user can retry without corrupting an existing installed model
