# Meeting metadata migration

M2 reads both version 1 and version 2 `metadata.json` files. A version 1 meeting is treated as a recorded, Internal/Restricted meeting with its audio at `recording.wav`. Reading it does not change the file. The first metadata update writes version 2 atomically and saves the unchanged original as `metadata.v1.json`. Existing source chunks and `recording.wav` are not moved.

Version 2 adds the meeting name, source kind, relative audio filename, privacy mode, and transcription state. New recorded and imported meetings default to `restricted`. An interrupted M1 recording can still be recovered after migration.

M3 keeps metadata schema version 2. It recognizes `restricted` and `cloud_permitted`; a missing or invalid `privacy_mode` is treated as `restricted` without rewriting the file on read. `active_minutes_version` is optional and appears only after a minutes version is created or selected. A meeting's `minutes/<version-id>/manifest.json` records its transcript run, origin, template, and review state; `content.json` holds the editable structured minutes and source segment references. These files are created by an atomic staging-and-rename operation. Editing or regenerating minutes creates a new version, leaving earlier approved content intact. Existing M2 `transcripts/<run-id>/original.json` and `working.json` are never migrated or rewritten for minutes generation.

To roll back from M3 to M2, close fahmm and run the earlier app. M2 ignores the optional metadata field and the `minutes/` directory; the audio and transcript runs remain usable. Keep the M3 files if you may return to M3. This is separate from the M1 rollback procedure below.

To roll back a migrated recording to the M1 application, close fahmm and copy that meeting's `metadata.v1.json` over `metadata.json`. M1 cannot read version 2 metadata. This rollback restores M1's metadata view, so any M2 name/transcription fields will not appear in M1; the M2 transcript files and audio remain on disk. Keep a separate backup of the meeting folder before a manual rollback.

## M4 deletion and recovery

The default local meeting root is `%LOCALAPPDATA%\fahmm\meetings`. Each meeting is a folder named with its 32-character ID. A confirmed deletion first renames the selected folder to `.deleting-<id>` in that same root, then removes its files. This is intentionally scoped to app-owned meeting data; it also removes the selected meeting's temporary files. The app refuses to traverse links or Windows reparse points during cleanup.

If Windows blocks a file removal, the folder may remain as `.deleting-<id>` and the UI reports an incomplete deletion. After closing an application holding the file, open **Meetings → Storage cleanup**, select the pending deletion, and click **Retry selected deletion cleanup**. Do not manually rename a tombstone back into a meeting: it may already be missing some files. The retry is limited to that ID, and a successful retry removes the tombstone. A crash during an import can leave `.import-<id>`; the same screen lists abandoned imports and requires a separate confirmation before removing the unfinished copy. An active import or a completed meeting is not eligible for this cleanup.

Deletion is irreversible within fahmm and is not secure erasure. The original file imported from elsewhere, exports chosen outside the managed folders, clipboard copies, and system or cloud backups are outside this cleanup. If you need to preserve a meeting, export it or back up its folder before confirming deletion. A deleted meeting cannot be recovered by the M1–M3 metadata rollback steps above.
