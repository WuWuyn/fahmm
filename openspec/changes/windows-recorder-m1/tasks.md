# Tasks

## 1. Application foundation

- [x] 1.1 Create a Python 3.12 project with uv, PySide6, and SoundCard; verify uv sync and that the launch command opens a Windows window.
- [x] 1.2 Separate UI/controller/audio/storage and document M1 launch in README; verify importing modules neither starts capture nor calls the network.

## 2. Storage and recovery

- [x] 2.1 Build a per-meeting store with versioned JSON metadata and atomically flushed/renamed WAV chunks; test unique folders and readable committed chunks.
- [x] 2.2 Mix both sources into a playback file, preserve gaps and source chunks; test signal in both channels and no audio from paused time.
- [x] 2.3 Detect unfinished sessions and recover valid WAV chunks even with stale metadata; test crash/corrupt chunks without affecting other meetings.

## 3. Windows audio capture

- [x] 3.1 Implement a WASAPI adapter that lists speaker loopbacks and microphones and opens the exact selected device; verify Windows enumeration and missing-source errors.
- [x] 3.2 Implement a session controller that starts both sources only after Record, supports Pause/Resume/Stop and mid-session errors; test its state machine with a fake source, idle silence, and no network egress.

## 4. Recorder UI

- [x] 4.1 Build an English UI with source selection, indicator, timer, Record/Pause/Resume/Stop, and clear errors; verify keyboard actions, button states, and UI responsiveness during simulated recording.
- [x] 4.2 Show unfinished sessions, a Recover action, and the playback file path; test UI/controller recovery and document it in README.

## 5. M1 integration acceptance

- [x] 5.1 Run unit/integration tests, lint, and OpenSpec strict validation; record actual results in docs/m1-verification.md.
- [ ] 5.2 Run AT-01/AT-02 during a permitted 20-minute Teams/Meet meeting with headphones and a microphone; listen to both channels and record the results in docs/m1-verification.md.
- [ ] 5.3 Run AT-10 by terminating the app during a real recording, reopening it, recovering audio, and verifying another meeting is intact; record the results in docs/m1-verification.md.
