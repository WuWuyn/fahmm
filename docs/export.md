# Export meeting documents

fahmm exports ordinary UTF-8 files from **saved** meeting data. Choose a minutes version for `minutes.md` and a transcript run for `transcript.txt`. An earlier version or run can be exported even when a newer one is active. Save or discard editor changes before exporting; unsaved text is never silently included.

## `minutes.md`

The Markdown starts with the selected version's review state. An unverified draft remains visibly unverified when opened in another app. The body uses Vietnamese headings and includes source start times where the saved structured items have citations. For example, a source-linked decision can appear as:

```markdown
> Review state: Unverified

# Chưa rõ
Ngày: Chưa rõ
Người tham dự: Chưa rõ

...

## Quyết định
- Đã thống nhất thử nghiệm. [0.0s]
```

When a reviewer saves free-form minutes edits, fahmm preserves the underlying draft's citations in a separate **Source references from the underlying draft** appendix. Its `HH:MM:SS.s` ranges are navigation aids, not proof that the edited sentences are supported by the recording. Approval is a user action; export does not approve a version or verify claims automatically.

## `transcript.txt`

The text file uses the selected run's corrected working transcript, one timestamped segment per line. It does not revert to the original ASR text when edits were saved. Example:

```text
[00:00:00.0–00:00:02.0] Đã thống nhất thử nghiệm.
```

## Where exported copies go

The Save dialog lets you choose an existing folder outside fahmm's managed meeting and model directories. The default filenames are `minutes.md` and `transcript.txt`. Replacing an existing file requires separate confirmation; a failed write leaves the earlier file intact. Exports are separate copies: deleting the meeting later does not delete them.

Choosing a shared drive or cloud-synced folder may make content accessible outside the device. Copy Markdown is also an explicit action, and other applications may read the system clipboard. Neither file export nor clipboard copy invokes the configured AI provider. Managed API keys and internal file paths are not added to the documents.
