# Tauri Windows first-run and acceptance guide

This guide is for the **internal v1 candidate**. Public release remains blocked by the [acceptance record](v1-release-acceptance.md) and [native license review](v1-native-license-review.md). Use the same candidate hash on Windows 10 x64 and Windows 11 x64 machines without development Python or FFmpeg. Record the OS build, device names, model revision, operator, date, and outcomes in the acceptance record without copying meeting content.

## Verify and start the portable candidate

Keep the ZIP and matching `.zip.sha256` file in one folder. In PowerShell, from that folder:

```powershell
$archive = '.\fahmm-tauri-0.1.0-windows-x64-portable.zip'
$expected = (Get-Content "$archive.sha256").Split(' ')[0].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'Candidate checksum mismatch' }
Expand-Archive -LiteralPath $archive -DestinationPath '.\fahmm-portable'
& '.\fahmm-portable\fahmm\fahmm-desktop.exe'
```

The candidate ZIP SHA-256 is `535faa477ea0cbf955668a6e428b8ac9ea369d3bcb3140adb0f411225791f3d3`. Check `fahmm/BUILD_INFO.json` after extraction: `sourceRevision` must be `2211d4494408bcb80897a861f256e58b42b6b698` and `sourceDirty` must be `false`. Keep `fahmm-sidecar.exe` beside `fahmm-desktop.exe`. The checksum, extraction, and process start commands have been exercised on the development host; clean-machine UI behavior remains pending.

The MSI candidate is `fahmm_0.1.0_x64_en-US.msi` (SHA-256 `e91c936cff9234948ee6a0cd5b784b284081cf69b3ee0be083f0a68179f4c606`). Verify it with `Get-FileHash` before installing. MSI administrative extraction and startup of its payload passed on the development host; the normal install flow still needs clean-machine testing. The NSIS setup candidate is `fahmm_0.1.0_x64-setup.exe` (SHA-256 `005906758ebb98843de4e3551e85d20c05889cd16c7f46d79be7f5891271869a`).

## First model, then offline use

On first launch, confirm that Recorder, Meetings, Models, and Settings open without a backend warning. Open **Models** and explicitly download a compatible multilingual Whisper model, such as Base. Record the repository and exact installed revision. No model weight is bundled with the app. Disconnect the machine from the network, close and reopen fahmm, and confirm the installed model remains selected. A normal recording or import, local transcription, and offline minutes draft must not require an account, API key, or GPU.

In **Recorder**, choose the speaker output and microphone, then use **Record**, **Pause**, **Resume**, and **Stop**. For the real-hardware gate, use only a call that participants have permitted to record. In **Meetings**, alternatively use **Import audio** for WAV, MP3, M4A, or FLAC. Select the installed model and Vietnamese, press **Transcribe**, review saved timestamped segments, play and seek the corresponding local audio, and save any corrections. Use **Offline draft** while the meeting remains **Internal/Restricted**; review source links and save the minutes version. An offline draft is extractive and needs human review.

Export the selected transcript with **Export TXT** and the selected minutes version with **Export MD**. Open both files with a separate text editor and verify readable UTF-8 and source timestamps. Select **Delete meeting…**, inspect the confirmation scope, cancel once, then confirm for the intended test meeting. Verify that another meeting, the original imported file, and exported documents remain. If deletion reports a locked file, use **Storage cleanup** after releasing the lock.

## Data, privacy, and rollback

Meeting data and downloaded models live under `%LOCALAPPDATA%\fahmm\meetings` and `%LOCALAPPDATA%\fahmm\models`, outside the portable folder. Exports are written to the location chosen in the save dialog. Deletion removes app-owned meeting data, not source imports, exports, backups, clipboard copies, or synced-folder copies; it is not secure erasure.

New meetings are Internal/Restricted. Do not change that mode for the offline test. For a separate provider test, use a disposable loopback endpoint, change only the test meeting to Cloud Allowed, inspect the destination and complete preview, try Cancel, then make a fresh preview and Confirm. Record request counts rather than payload text. Do not use a real provider or private meeting content for this acceptance check.

To roll back, close Tauri and ensure its sidecar has stopped. Keep a backup of personal meeting data before testing any older build. Verify the earlier Qt candidate ZIP and extract it to a separate folder, then run its `fahmm.exe`. It reads the same `%LOCALAPPDATA%\fahmm` library; never run the two UIs concurrently. See [portable.md](portable.md) for the Qt ZIP's checksum and extraction commands. The rollback test on the development host is recorded in [tauri-verification.md](tauri-verification.md); repeat it on a disposable profile before relying on it for a release.
