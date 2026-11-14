# fahmm portable Windows build

This is a Windows 10/11 x64 release candidate. It runs from an extracted folder without installing Python, a separate FFmpeg executable, an account, a server, an API key, or a GPU. The package does **not** include Whisper model weights.

## Verify, extract, and start

Keep the `.zip` and matching `.zip.sha256` file together. In PowerShell, compare the published checksum with:

```powershell
Get-FileHash .\fahmm-0.1.0-windows-x64.zip -Algorithm SHA256
Get-Content .\fahmm-0.1.0-windows-x64.zip.sha256
Expand-Archive .\fahmm-0.1.0-windows-x64.zip -DestinationPath .\fahmm-portable
.\fahmm-portable\fahmm\fahmm.exe
```

The two hex values must match. You can move the extracted `fahmm` folder later; the meeting library remains in the Windows profile. Launching a second copy against the same profile is refused to protect local data.

## First model install and offline use

The app opens on **Recorder**. It can record or import audio before a model is installed. To transcribe, connect to the internet once, open **Models**, and explicitly download a compatible multilingual Whisper model such as Base. The model is stored under `%LOCALAPPDATA%\fahmm\models`, outside the application folder. Downloading is never automatic. After the model is installed, disconnect if you wish: **Meetings → Transcribe → Create offline draft → Export minutes.md** works locally, without an API key. The offline draft is extractive and needs review; it is not a semantic LLM summary.

For recording, choose your speaker output and microphone in **Recorder**, then Record, Pause/Resume, and Stop and save. In **Meetings**, you can also import WAV, MP3, M4A, or FLAC. Review and save transcript edits before export. Select the saved transcript run for **Export transcript.txt**, or a saved minutes version for **Export minutes.md** or **Copy Markdown**. Exported documents are ordinary files at the location you choose. Shared folders, synced drives, and the clipboard may expose their contents to other software.

New meetings default to **Internal/Restricted**. Audio, transcripts, and offline minutes stay in `%LOCALAPPDATA%\fahmm\meetings`. Provider use is optional: only a meeting deliberately changed to **Cloud permitted** can send selected transcript text, and each send shows the destination and complete payload for confirmation. A remote OpenAI-compatible endpoint is still remote processing. Provider profiles and protected keys remain under the local Windows profile; the portable folder contains no user credentials.

To remove a meeting, select it in **Meetings**, click **Delete meeting…**, review its name and scope, and confirm. The app removes its own audio, transcript runs, minutes, metadata, and temporary files. It leaves the original file imported from elsewhere, exports, clipboard copies, and backups untouched. This is ordinary deletion, not secure erasure. If Windows blocks removal, use **Meetings → Storage cleanup → Retry selected deletion cleanup** after releasing the file lock. That screen also offers a separately confirmed cleanup for an abandoned import.

See `README.md`, `THIRD_PARTY_NOTICES.md`, `RUNTIME_DEPENDENCIES.txt`, and `BUILD_INFO.json` inside the extracted folder. Detailed workflows are in the source repository's `docs/` directory.
