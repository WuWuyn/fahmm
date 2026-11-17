# Proposal

## Why

FAHMM's current minutes template covers generic summaries, topics, decisions, action suggestions, and questions. Customer-facing IT and software engineering meetings also need requirements, proposals, risks, incident findings, and UAT observations kept distinct so a draft does not turn discussion into an approved commitment. This change defines that domain while retaining the existing local-first Flow 1 and Flow 2 behavior.

## What Changes

- Add one common Vietnamese-first minutes structure with a selected meeting type: requirement gathering, technical discussion, project status, issue/incident, UAT/customer feedback, or general. Type-specific sections are optional views of the same stored domain, not separate incompatible templates.
- Add source-linked candidate entries for requirements, decisions, proposed solutions, open questions, risks/blockers, action suggestions, and next steps. Label suspected causes, unapproved proposals, and unconfirmed customer feedback explicitly.
- Require human review of material claims and customer-facing metadata. Generated text may summarize cited discussion but cannot invent attendees, owners, deadlines, approvals, or formal requirements.
- Preserve version provenance and exported review labels. Older minutes remain readable and exportable without an eager rewrite; new structured drafts are saved as new versions.
- Define testable generation, editing, source review, export, privacy, and migration behavior. No application code is changed by this proposal.

## Capabilities

### New Capabilities

- `it-customer-minutes`: Structured, evidence-linked minutes for the five customer-facing IT/SE meeting types, with conservative classification and review rules.

### Modified Capabilities

None. `openspec list --specs` currently reports no main capability specs. This change extends the implemented M3 minutes product behavior without replacing the unarchived `minutes-privacy-m3/meeting-minutes` change.

## Impact

- **Users and goals:** Engineers, BAs, PMs, technical leads, and solution architects can produce reviewable customer-facing records that distinguish agreed decisions from proposals and unresolved matters.
- **Likely implementation areas:** `src/fahmm/offline_minutes.py`, `provider_minutes.py`, `minutes_store.py`, `meeting_export.py`, the minutes bridge operations, and `desktop/src/features/minutes/MinutesPanel.tsx`. Transcript runs, timestamps, recording/import, and the existing provider authorization boundary remain authoritative.
- **Scope boundary:** Action entries remain suggestions. Independent task lifecycle belongs to `source-linked-action-items`; project assignment and cross-meeting search belong to `local-project-workspaces-search`. This change adds no Jira integration, team sync, speaker identification, local LLM, or new external service.
- **Compatibility:** Additive versioned minutes content and read/export support for old content; no eager migration of meetings or transcripts. Any new bridge fields require the existing protocol/fixture checks. A rollback must leave older versions and approved content intact.
- **Privacy and non-functional requirements:** Restricted meetings remain entirely local; offline drafting remains extractive without a local LLM. Cloud generation still requires a Cloud permitted meeting and per-send preview/confirmation of selected reviewed transcript content. Vietnamese is the default output language; English technical terms are preserved.
- **Dependencies and risks:** Depends on saved reviewed transcript runs and M3 versioning/source navigation. Risks include false classification from keyword extraction, plausible unsupported provider claims, edited transcript drift, and freeform Markdown losing claim-level citation placement. The design requires explicit uncertainty and a review path for each risk.

Acceptance is defined by Given/When/Then scenarios in `specs/it-customer-minutes/spec.md`; the mapping from requirements to scenarios and tasks is in `analysis.md`.
