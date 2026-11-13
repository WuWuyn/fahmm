# Proposal

## Why

fahmm needs an initial Windows build that can record real meetings without a bot or network service. M1 establishes local audio capture and recovery before ASR and minutes are built in later milestones.

## What Changes

- Add an English Recorder UI for selecting speaker output and microphone, then Record, Pause/Resume, and Stop.
- Capture WASAPI loopback and microphone simultaneously, keep both sources locally, and produce a playback file containing both.
- Persist short audio chunks periodically so an interrupted recording can be recovered on restart.
- Display elapsed time, state, and device errors; activate audio capture only after Record.
- Automate state and recovery tests, then manually accept AT-01, AT-02, and AT-10 on Windows hardware.

## Capabilities

### New Capabilities

- audio-recording: Control and capture simultaneous Windows system and microphone audio.
- recording-recovery: Persist and recover unfinished recording sessions.

### Modified Capabilities

None.

## Impact

M1 adds a Python/PySide6 desktop app, a WASAPI adapter, per-meeting file storage, run instructions, and tests. It adds no backend, account, telemetry, or provider calls.
