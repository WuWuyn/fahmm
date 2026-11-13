# M1 Recorder verification

Checked on 14 November 2026 on Windows x64. This log distinguishes completed checks from the real-meeting acceptance tests that remain open.

## Automated checks and UI inspection

| Check | Result | Evidence |
| --- | --- | --- |
| uv sync --locked | Passed | Python 3.12.14, uv 0.13.8, PySide6 6.12.0, SoundCard 0.4.6, numpy 2.5.4 |
| uv run pytest -q --tb=short | Passed | 14 tests: storage, mixing, recovery, process termination with fake audio, state machine, stopping during device startup, network blocking, side-effect-free imports, UI, and keyboard shortcuts |
| uv run ruff check . | Passed | No lint errors |
| uv run ruff format --check . | Passed | All files formatted |
| openspec validate windows-recorder-m1 --strict | Passed | Change is valid |
| openspec doctor --json | Passed | Project root reports healthy: true |
| uv run fahmm --smoke | Passed | Qt window opened and closed with exit code 0 |
| Recorder window inspection on Windows | Passed | Listed Speakers (Realtek(R) Audio) as loopback and Microphone Array (Realtek(R) Audio) as microphone; initial state was idle with Pause/Stop disabled |
| Direct UI exercise with fake audio | Passed | Record advanced the timer and enabled Pause/Stop; Pause held the timer at 18 seconds; Resume continued; Stop created recording.wav and showed its path. UI remained responsive. |

Qt tests with fake audio confirmed controls and shortcuts while recording. One pytest run hung when it ran concurrently with a separate Qt smoke window, apparently because both windows competed for focus. A subsequent standalone pytest run passed. Run UI checks sequentially.

## User-triggered real-device Record/Stop trial

On 14 November 2026, the user pressed Record and then Stop and save. Technical inspection found completed metadata and a 48 kHz stereo PCM recording.wav lasting 9.59 seconds (460,288 frames; 1,841,196 bytes). There were five system chunks and five microphone chunks, with none skipped. Both channels contained nonzero samples, but system RMS was 7.9/32767 versus microphone RMS of 649.1/32767. The audio content was not played or transcribed, so system-audio audibility is unverified. This trial confirms Record → Stop → saved file, not the full AT-01/AT-02 acceptance tests.

## Real-hardware acceptance still required

| ID | Status | Required check |
| --- | --- | --- |
| AT-01 | Not run | Record a permitted 20-minute Teams/Meet meeting with headphones and mic. Listen to recording.wav: left/system and right/mic must both be clear, and no bot must join. |
| AT-02 | Partial | Record/Stop produced a valid WAV in the 9.59-second trial. Still verify Pause/Resume, timer behavior, and excluded paused audio on real hardware. |
| AT-10 | Not run | After at least one chunk is flushed in a real recording, terminate the app, reopen it, recover the session, and confirm that another meeting remains intact. |

Use only meetings or audio approved for recording. Do not mark M1 accepted until these results are recorded.
