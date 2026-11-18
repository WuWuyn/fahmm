# Design: One-click meeting minutes

## Context

See `proposal.md`. The desktop already loads the active transcript run, calls `minutes.generateOffline`, reads saved minutes versions, renders the `domain_schema_version: 1` payload, edits claims, and exports Markdown. `OfflineMinutesService` creates an atomic version through `MinutesStore`; provider generation uses a separate preview/confirm path. The current `general` draft extracts only a small number of topics and does not populate every common section. There is no bundled local semantic LLM.

## Goals / Non-Goals

**Goals:** Make the primary creation path one click from a usable saved transcript; produce a reviewable universal draft with broad temporal coverage, stable claim IDs, source snapshots, explicit uncertainty, and safe versioning; keep the existing optional provider and specialized legacy versions readable.

**Non-Goals:** Claim semantic summarization without a local model; send Restricted content to a provider; infer absent meeting metadata or people; introduce a second minutes schema, task manager, diarization, or a new model dependency.

## Decisions

1. **Reuse the domain schema and minutes store.** New drafts use `domain_schema_version: 1` and `meeting_type: general`. The existing metadata fields, section keys, claim IDs, review states, source snapshots, and atomic version commits already cover the universal structure. Existing type-specific versions retain their stored type and render through the current reader. A schema migration would duplicate data without adding user value.
2. **Keep the primary path fully local and name it honestly.** One click invokes the existing offline minutes bridge operation with a fixed universal type; it neither selects a provider nor changes meeting privacy. The result remains an `extractive`, `unverified` draft. The optional provider workflow stays separate because the current privacy contract requires preview and confirmation of each send. The Whisper ASR model is not a summarization model.
3. **Make the universal extractor evidence-first.** Select representative discussion segments from bounded chronological windows spanning the working transcript, then classify explicit requirement, decision, proposal, action, question, risk, and next-step cues. Preserve cited working text and technical terms verbatim; keep requirements as candidates, action owners/deadlines unknown unless the source explicitly states them, and ambiguous decisions as proposals or unresolved items. Bound each section and deduplicate normalized text within that section. Keep the existing specialized extractors for older advanced generation paths.
4. **Use the existing bridge contract.** `minutes.generateOffline` already accepts the active run, validates it in the backend, and returns a new version ID. The primary UI sends `meetingType: general` without exposing a selector or prompt. No new native path or wire operation is needed; the contract and protocol fixtures remain stable.
5. **Regenerate by creating a new version.** The UI checks for unsaved freeform or domain edits before another generation and explains that saved versions remain available. On success it selects the new version; on failure it leaves the current version selected and shows a retryable message. The button is disabled while a request is active or no usable text is available.
6. **Render all universal sections.** The `general` review displays the same stable section order even when a section has no supported claim. Markdown export reads the selected saved version and uses the same order and explicit empty-section wording. Other stored meeting types keep their existing rendering behavior.

## Data flow

`MinutesPanel` loads the active run's working segments → user presses Generate meeting minutes → `minutes.generateOffline` resolves the active run → universal extractor builds a validated domain payload → `MinutesStore.save_version` commits a new unverified version → UI refreshes, selects it, and renders source-linked fields → edits create another version → existing Markdown export renders that selected version.

## Validation and error handling

- Missing or blank transcripts fail before any version is written. Generated sources are checked against exact run IDs, segment IDs, timestamps, and excerpts at commit time.
- Generated claims remain `needs_review`; no candidate requirement or action suggestion becomes approved by generation. Risk cues remain risks unless the transcript explicitly names a blocker.
- Storage or extraction failure leaves previous versions intact. The UI gives a clear retry path and does not replace saved work.
- Provider JSON normalization and its authorization boundary are unchanged; existing deterministic mock tests remain the evidence for malformed provider output.

## Risks / Trade-offs

- **Extractive quality:** Without a local LLM, the summary can be less fluent than an AI paraphrase. Label it as extractive and prioritize source coverage and editability.
- **Keyword ambiguity:** A cue may be present in a negated or hypothetical statement. Use conservative exclusions and leave all generated claims unverified, with direct source navigation.
- **Large output:** Long recordings can yield many matches. Limit discussion windows and claims per section while covering early, middle, and late periods.
- **Unreviewed previous draft:** A new version may appear while an old one exists. Preserve the old version, require confirmation for unsaved edits, and keep version selection visible.

## Migration Plan

No stored-data migration. New universal versions use the existing format; old versions remain readable and exportable. Reverting the UI/extractor changes leaves saved versions valid under the existing domain validator.
