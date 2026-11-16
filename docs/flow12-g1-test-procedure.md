# G1 real-device recording acceptance procedure

This procedure covers AT-01, AT-02 and AT-10 plus the missing/unplugged/wrong-output and quiet-loopback checks in `flow12-quality-gates` tasks 1.1–1.5. It is a **procedure, not an acceptance result**. Use only a Teams/Meet call that every participant has permitted to be recorded. A designated listener and an engineering reviewer must record their observations; PCM levels or automated tests alone cannot pass G1.

## Candidate and test setup

Use the internal portable candidate prepared from code commit `1352c90feeff95baf707938b712c28fc1a196e26`. Its ZIP is `.build/release/fahmm-tauri-0.1.0-windows-x64-portable.zip`, SHA-256 `8617a26b5cb48a97219309afbf7bfe19f6ade90de200da8a5f4b2b886e28c0db`. Its `BUILD_INFO.json` says `sourceDirty: false`; both embedded executable hashes were verified in the [preflight record](evidence/flow12-g1-preflight-2026-11-16.md). The old `2211d44` candidate must not be used to accept current code. If recording code or the candidate changes, rebuild and record a new SHA before testing.

1. Use a dedicated Windows test account or otherwise isolated fahmm data root. Keep all audio and notes with meeting content local; do not add them to Git. Record Windows edition/build, app ZIP SHA, test date/timezone, SoundCard version if known, Teams/Meet version, selected system output/loopback and microphone names/IDs, headset model, and the person who confirmed recording permission. Keep the meeting in Internal/Restricted mode. Confirm no bot joined.
2. Verify the ZIP hash with `Get-FileHash -Algorithm SHA256` and extract it to a fresh folder. Check `BUILD_INFO.json` revision/hash, then run `fahmm-desktop.exe` with `fahmm-sidecar.exe` beside it. This is an internal candidate; it has not passed G6 clean-machine acceptance.
3. In **Recorder**, select the output that the call actually uses and the intended microphone; use **Refresh audio devices** if needed. Confirm idle status, timer at zero, and no live input levels before Record. Make a brief permitted sound from the remote side and locally after Record to identify the channels. The saved `recording.wav` is 48 kHz PCM stereo: left = system/loopback, right = microphone. Its per-source chunks are committed about every two seconds.
4. Create and save a separate, harmless control meeting before the crash test. Record its `recording.wav` and `metadata.json` SHA-256 values. Do not delete or modify this meeting until AT-10 is complete.

## Run A — AT-01 and AT-02: live call and pause timing

1. Record a permitted Teams/Meet call lasting at least 20 minutes, with headphones connected throughout. Note the wall-clock time when the UI changes to **Recording**, not only the Record click. Observe both source-level indicators at the beginning, middle and end. Arrange consented remote and local speech markers near those points; do not put their wording in public evidence.
2. During the call, press **Pause** for a clearly timed interval, preferably at least 20 seconds. Note Pause and Resume wall-clock timestamps, UI states, and timer values. Arrange a distinct consented marker during the paused interval. Check that the timer stops advancing while paused and resumes afterward. Note any source-level behavior. Press **Resume**, continue the call, then **Stop**; wait for **Saved** and note the final UI timer and wall-clock time.
3. Reopen the saved meeting under **Meetings** and play the beginning, middle, end, and both sides of the pause boundary. With stereo headphones, listen to the left/system and right/microphone channels independently. Record whether remote and local speech are intelligible and correctly routed, whether either channel is clipped, silent, too quiet or drifts, and whether the paused marker is absent. A nonzero meter or RMS is insufficient.
4. Compute `expected active seconds = Stop time − Recording-state time − sum(Resume time − Pause time)`. Compare this with the displayed final timer and WAV duration; record all three numbers and their differences. Do not invent a pass tolerance: if the discrepancy affects understanding or any paused material is present, fail AT-02 and investigate. On the development machine, the following prints metadata only and does not export speech:

   ```powershell
   $wav = Join-Path $env:LOCALAPPDATA 'fahmm\meetings\<meeting-id>\recording.wav'
   & 'D:\fahm\.venv\Scripts\python.exe' -c 'import sys,wave; f=wave.open(sys.argv[1]); print("channels=",f.getnchannels(),"rate=",f.getframerate(),"seconds=",f.getnframes()/f.getframerate())' $wav
   (Get-FileHash -LiteralPath $wav -Algorithm SHA256).Hash
   ```

Pass AT-01 only if the permitted 20-minute call is saved, both voices are intelligible on their expected channels, playback works after reopening, and no bot joined. Pass AT-02 only if idle capture does not start early, controls/states/timer are truthful, the WAV is valid, and the paused interval is absent from both channels.

## Run B — AT-10: interrupted capture and independent meeting integrity

1. Start a **second** permitted recording. Wait until both `system/` and `microphone/` contain at least one committed `.wav` chunk (normally more than two seconds; use five seconds or longer to allow flush). Note the new meeting ID and the last committed chunk times. Do not use the 20-minute Run A meeting as the control.
2. While status is **Recording**, force-close only the fahmm desktop instance using Task Manager. Do not press Stop. Attempt to reopen the same candidate without first removing an orphaned sidecar; if it cannot reopen, record the failure before any cleanup. In **Recorder → Recover recordings**, select the interrupted meeting and press **Recover**. Note any skipped/damaged chunk count and error text; a missing or unrecoverable session fails AT-10.
3. Reopen the recovered meeting and listen to its saved audio. Compare the control meeting's `recording.wav` and `metadata.json` hashes with the values from setup; both must match. Record whether both channels contain the committed part. Do not expect uncommitted tail audio to survive, and report any gap honestly.

## Run C — device failures and quiet system audio

Use disposable sessions; do not disrupt a real participant's hardware without agreement. Record one row per case with device selection, UI state/error, whether a meeting was created, and recoverability.

| Case | Procedure | Required observation |
| --- | --- | --- |
| Missing source before Record | Select a detachable device, disconnect it, refresh devices, then try Record only if the UI still offers it. Repeat for loopback/output and microphone where hardware permits. | The unavailable source is identified; the UI never claims both sources are recording. |
| Unplug during recording | In a short permitted test, unplug a detachable mic or output after chunks commit. | The failing source is identified, recording state is truthful, committed data remains recoverable. |
| Wrong playback output | Select output A in fahmm but route the call audio to output B. | Report meter and listening results. Silence on the selected loopback cannot count as successful two-source capture even if the UI says Recording. |
| Quiet system channel | Replay remote and local markers separately. Check call output routing, Windows app/device volume and mute, selected SoundCard/WASAPI loopback, headset connection, and clipping. Repeat with corrected routing/volume. | Record before/after listening results and level readings. If remote speech remains unintelligible, block G1 and scope an FR-07 preflight/gain fix. |

If a physical disconnect case cannot be performed, mark it **NOT RUN** with the reason; do not turn it into a pass. Do not change device routing halfway through the 20-minute run used for AT-01.

## Evidence and decision

For **each run**, copy [the gate evidence template](gate-evidence-template.md) to `docs/evidence/flow12-g1-YYYY-MM-DD-<run>.md`. Include the full code commit, candidate SHA, OS/build, device names, permission statement, wall-clock and UI timestamps, active/WAV durations, channel-by-channel listener findings, failure matrix results, control-meeting hashes, actual errors and any retest. Reference local recording hashes and paths only; never commit audio, meeting transcript, speaker names or call content. Record tester, listener, reviewer and dates. Keep task checkboxes 1.1–1.5 unchecked until the named run has passed on this candidate. An engineering reviewer and product owner decide G1 after all mandatory cases are supported; G0's automated result does not sign G1.
