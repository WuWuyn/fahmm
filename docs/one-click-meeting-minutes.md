# One-click meeting minutes

## Desktop journey

1. Record or import a meeting, then run local transcription. Review and save any transcript corrections.
2. Open the meeting's **Minutes / Biên bản** tab. Press **Generate meeting minutes / Tạo biên bản**. No meeting type, template, provider profile, or prompt is required.
3. The selected active transcript run produces a new, unverified, source-linked draft on this device. It opens automatically. Use each claim's source button to inspect the saved excerpt and seek the corresponding audio time.
4. Correct meeting metadata and claims, mark reviewed claims, and save a new version. The previous draft remains available in **Saved version / Phiên bản đã lưu**. Approve only after reviewing the claims and any transcript drift.
5. Use **Copy Markdown / Sao chép Markdown** or **Export MD / Xuất MD** to export the selected saved version. Unsaved edits must be saved or explicitly discarded first.

The action is disabled when the active transcript is missing or contains only blank text. A failed generation leaves existing minutes intact and permits retry. Regeneration asks before discarding unsaved edits and creates a separate unverified version.

## What the draft means

The local generator selects transcript excerpts across the meeting and classifies explicit cues into summary, discussion, candidate requirements, decisions, proposals, action suggestions, questions, risks, next steps, and technical considerations. Every generated claim has a saved transcript citation. Unknown participants, dates, owners, deadlines, and unsupported sections stay unknown or empty. An action suggestion is not an assigned task. The summary is extractive, **not a semantic AI summary**; its wording and classification need human review. Long meetings are represented by bounded selections from across the time span, not by a verbatim copy of every spoken line.

**Advanced draft options / Tùy chọn bản nháp nâng cao** keeps specialized meeting types available. The separate optional provider flow requires a cloud-permitted privacy classification, selected and reviewed transcript segments, an exact payload preview, and confirmation for each send. The primary action never sends meeting content to a provider. A future local semantic model would require its own implementation and acceptance criteria.

## Acceptance boundary

Automated fixtures verify versioning, citations, empty fields, chronological coverage, export, network-blocked generation, and UI states. A real one-hour Vietnamese recording, speech accuracy, audio source capture, and clean Windows package are separate manual acceptance gates.
