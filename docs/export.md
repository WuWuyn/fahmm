# Export meeting documents

fahmm exports ordinary UTF-8 files from **saved** meeting data. Choose a minutes version for `minutes.md` and a transcript run for `transcript.txt`. An earlier version or run can be exported even when a newer one is active. Save or discard editor changes before exporting; unsaved text is never silently included.

## `minutes.md`

The preview, clipboard copy, Markdown and Word exports show the text of each decision. For example, the minutes can contain the following entry.

```markdown
# Chưa rõ
Ngày: Chưa rõ
Người tham dự: Chưa rõ

...

## Quyết định
- Đã thống nhất thử nghiệm.
```

Reviewers can open a note in the structured editor to look up its linked transcript segments.

## `transcript.txt`

The text file uses the selected run's corrected working transcript, one timestamped segment per line. It does not revert to the original ASR text when edits were saved. Example:

```text
[00:00:00.0–00:00:02.0] Đã thống nhất thử nghiệm.
```

## Where exported copies go

The Save dialog lets you choose an existing folder outside fahmm's managed meeting and model directories. The default filenames are `minutes.md` and `transcript.txt`. Replacing an existing file requires separate confirmation; a failed write leaves the earlier file intact. Exports are separate copies: deleting the meeting later does not delete them.

Choosing a shared drive or cloud-synced folder may make content accessible outside the device. Copy Markdown is also an explicit action, and other applications may read the system clipboard. Neither file export nor clipboard copy invokes the configured AI provider. Managed API keys and internal file paths are not added to the documents.
