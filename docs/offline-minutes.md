# Offline minutes drafts

An offline draft uses the **edited working transcript** of the selected transcription run. It works without an internet connection, provider profile, API key, account, GPU, or local LLM. A Restricted meeting stays Restricted throughout this process.

After recording or importing audio, finish local transcription and review the timestamped transcript. The offline draft action creates a **new unverified version** under that meeting. Each summary excerpt, topic, explicit decision, action, and open question points to the transcript segment and audio timestamp it came from. Open a citation to inspect the edited transcript and play the source audio before approving the minutes. Edits and regeneration make new versions; an approved version remains available unchanged.

An edited version records the immediate parent version and retains whether its original draft was extractive or provider-generated. The UI and exported Markdown identify that source and state that user edits are not automatically verified. Every minutes export also says that any action items in the document are suggestions until independently tracked tasks exist, even when the structured action list is empty or no longer matches edited Markdown.

The draft is **extractive**: it chooses and groups transcript excerpts. It does not understand the meeting like a person or produce a complete semantic AI summary. It may miss a decision or action, and a segment with a matching phrase still needs human review. It does not identify speakers. Unsupported attendee, owner, due-date, or decision fields show `Chưa rõ`. The default headings are Vietnamese in both interface languages; the English/Vietnamese switch changes application controls, not saved draft content. You can edit the template's headings, guidance, and topic count for future drafts without rewriting older versions.

If the transcript is empty, transcribe or select a completed run first. If a draft fails, the audio, transcript, and earlier minutes versions remain available. The app does not switch to a provider automatically.

The backend workflow is exercised by `uv run pytest -q tests/test_offline_minutes.py tests/test_minutes_store.py`. It creates a controlled test meeting with a transcript, generates a draft with network sockets blocked, follows source IDs/timestamps, edits the working transcript, regenerates with a changed template, and confirms the earlier approved content is unchanged. The Meetings screen integration is covered separately in the M3 UI tasks.
