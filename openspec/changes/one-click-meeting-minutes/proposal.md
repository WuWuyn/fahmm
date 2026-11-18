# Proposal: One-click meeting minutes

## Why

The saved transcript already supports source-linked, versioned minutes, but the current desktop flow asks users to select a meeting type and exposes template and provider controls before the primary action. A user should be able to open a transcribed meeting, click one button, and immediately review a structured draft without configuring output.

## What Changes

- Add a primary **Generate meeting minutes / Tạo biên bản** action that uses the active saved transcript and one universal minutes structure.
- Build an unverified local draft with meeting information, summary, discussion points, requirements, decisions, proposed solutions, action suggestions, open questions, risks and blockers, and next steps. Empty sections remain visible for review. Cite transcript evidence for generated claims and retain unknown metadata, owners, and deadlines.
- Improve coverage of long transcripts and separate explicit decisions from proposals. Preserve technical terms and the transcript's language.
- Save each generation as a new version, open it automatically, preserve earlier approved and edited versions, and guard unsaved edits during regeneration.
- Keep editing, source navigation, Markdown export, legacy minutes, and optional provider generation compatible. The primary Restricted path stays offline and is labeled extractive; it does not claim a semantic AI summary.

## Capabilities

### New Capabilities

- `minutes-drafting-workflow`: One-action creation, review, regeneration, and export of a universal source-linked minutes draft from a saved transcript.

### Modified Capabilities

None. Main specs are not yet populated; this change extends the implemented M3 minutes behavior and the completed `meeting-minutes-it-customer-domain` change without replacing their versioned data or privacy contracts.

## Impact

- **Code:** Offline domain extraction, minutes bridge contract, React minutes panel and domain review, Markdown rendering, tests, and Flow 2 traceability.
- **Compatibility:** Reuse `domain_schema_version: 1`, `meeting_type: general`, claim IDs, source snapshots, and atomic `MinutesStore` versions. No eager migration or rewrite of previous minutes.
- **Privacy:** No automatic provider request, cloud fallback, API key, or new local LLM. The existing provider path retains its separate payload preview and explicit confirmation.
- **Scope exclusions:** Automatic task tracking, speaker identity, team collaboration, new provider integration, and customer approval workflow.
