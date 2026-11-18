# Customer-facing IT/SE Meeting Minutes — domain analysis

Analysis baseline: repository `main` at `7a3f651a420c20b44d84513fd8c2281d5f794796`, reviewed on 17 November 2026 (Asia/Bangkok). This is a planning document, not implementation or acceptance evidence. No `AGENTS.md` exists in the repository tree; `openspec/config.yaml`, the existing change specs, and `CONTRIBUTING.md` were used. OpenSpec CLI 2.0.0 reports no main specs and uses the `spec-driven` change schema.

## 1. Repository findings and current architecture

The current local flow is saved audio → versioned transcript run (`original.json` and mutable `working.json`) → generic minutes draft → local minutes version → review/edit/export. The transcript store preserves original ASR output while edits change the working copy ([`transcripts.py:86–89, 129–140`](../../../src/fahmm/transcripts.py)). New meetings are Restricted by default, with local metadata and one meeting folder ([`storage.py:40–81`](../../../src/fahmm/storage.py)).

| Area | Observed behavior and evidence |
| --- | --- |
| Generic structure | `DEFAULT_TEMPLATE` has title, date, attendees, summary, topics, decisions, actions, and open questions; the user can edit headings/guidance/topic limit ([`minutes_store.py:17–83`](../../../src/fahmm/minutes_store.py)). |
| Offline generation | `extract_minutes` selects representative excerpts and uses keyword lists for decisions/actions/questions. It sets attendee and missing action fields to `Chưa rõ`; it uses meeting `created_at` for the displayed date ([`offline_minutes.py:15–17, 77–145`](../../../src/fahmm/offline_minutes.py)). It is an extractive draft, not a semantic summary. |
| Optional provider generation | A Cloud permitted meeting and selected/reviewed transcript IDs are required before preview; the request includes selected working text and prompt, and confirmation is single-use ([`cloud_minutes.py:43–80, 107–191`](../../../src/fahmm/cloud_minutes.py)). Provider normalization accepts generic summary/topics/decisions/actions/questions and flags claims for review ([`provider_minutes.py:25–129`](../../../src/fahmm/provider_minutes.py)). |
| Persistence and provenance | Each version has a separate content file and manifest with `run_id`, origin, parent, source origin, review state, and atomic staging. Edits create a new version; approval updates the manifest ([`minutes_store.py:85–146, 207–227`](../../../src/fahmm/minutes_store.py)). |
| Citation validation | Existing saves check run ID, segment ID, and nonnegative timestamp shape, but do not compare a citation's times or text with that segment's current or historical working text ([`minutes_store.py:150–173`](../../../src/fahmm/minutes_store.py)). |
| User workflow | The minutes panel creates offline/provider versions, permits whole-body Markdown edits, approval, copying/export, and source seek/open controls ([`MinutesPanel.tsx:100–264`](../../../desktop/src/features/minutes/MinutesPanel.tsx)). |
| Export | Markdown is rendered from saved content and labels review state, draft origin, and action suggestions. `user_text` replaces the structured body; underlying citations then appear in a separate appendix explicitly not verifying that edit ([`meeting_export.py:32–64, 129–183`](../../../src/fahmm/meeting_export.py)). |
| Existing acceptance | `docs/traceability-map.md` maps FR-20–25/AT-05/09 to services, UI, and controlled tests; it explicitly says real evidence and complete action management are still open ([`traceability-map.md:15–27`](../../../docs/traceability-map.md)). |

The M3 [`meeting-minutes` delta](../minutes-privacy-m3/specs/meeting-minutes/spec.md) defines generic source-linked minutes and versions. [`source-linked-action-items`](../source-linked-action-items/proposal.md) separately plans durable tasks, and [`local-project-workspaces-search`](../local-project-workspaces-search/proposal.md) separately plans project assignment/search. [`flow12-quality-gates`](../flow12-quality-gates/specs/flow2-acceptance/spec.md) keeps action suggestions distinct from tracked work. This change adds a domain-specific structure and review contract; it does not replace or declare those changes implemented.

## 2. Capability gap analysis

| Capability | Classification | Evidence / gap |
| --- | --- | --- |
| Generic Vietnamese minutes template | Implemented | Fixed headings and template settings in `minutes_store.py:17–83`. |
| Offline source-linked extractive draft | Implemented | `offline_minutes.py:77–151`; semantic quality is intentionally limited. |
| Opt-in provider draft and privacy gate | Implemented in code; manual acceptance pending | `cloud_minutes.py:107–191`; AT-05–08 still need current-build gate evidence in `flow12-quality-gates/tasks.md`. |
| Saved versions, edits, approval, Markdown export | Implemented | `minutes_store.py:85–227`, `meeting_export.py:32–183`, `MinutesPanel.tsx:126–264`. |
| Claim-level evidence after transcript edits | Partially implemented | Segment links exist, but no saved cited excerpt or drift check; freeform edits have only underlying references. |
| Correct actual meeting date and customer metadata | Partially implemented | Generic title/date/attendees exist, but `created_at` can be an import time and customer/project/objective have no domain fields. |
| Requirement kinds, formal status, proposals, risks, incident certainty, UAT states | Missing | Neither current generic content nor provider normalizer has these fields. No type selector appears in `MinutesPanel.tsx`. |
| Structured claim review and customer sign-off distinction | Partially implemented | Document approval exists; there is no per-claim review state or customer acceptance/signature workflow. The latter remains outside this MVP. |
| Independent action manager | Specified but not implemented | `source-linked-action-items/tasks.md` has all implementation tasks open; current minutes warn that actions are suggestions. |
| Project/workspace search and reusable context | Specified but not implemented | `local-project-workspaces-search/tasks.md` is open; no project/customer entity is assumed here. |
| Quality on representative customer IT/SE conversations | Unknown / requires verification | Controlled tests cover generic minutes and privacy, not reviewed real customer meetings across the five types. |

## 3. Domain profiles and wording rules

All profiles share the common minutes fields below. Selecting a type changes relevant prompts, review labels, and visible optional sections; it does not create a second storage format.

| Meeting type | Capture separately | Critical distinction |
| --- | --- | --- |
| Requirement gathering | Business/functional/non-functional requirements, business rules, constraints, assumptions, open questions, changes | A discussed request is a candidate; a formal requirement needs explicit evidence and author confirmation. |
| Technical discussion | Architecture, technology, API/integration, database, security, performance, dependencies, alternatives | An option under discussion is a proposal; an agreed choice is a decision candidate with evidence. |
| Project status | Progress, milestones, issues, blockers, risks, dependencies, next steps | A forecast or target date is not a committed deadline without evidence. |
| Issue/incident | Problem, impact, investigation findings, suspected/confirmed causes, workarounds, resolution proposals, follow-ups | “Might be the cause” remains suspected, even if the same phrase appears under a cause heading. |
| UAT/customer feedback | Test scenario, observed result, feedback, defect, change request, pending confirmation | An observation or request is not customer acceptance. |

## 4. Proposed MVP field contract

`R` means required in a saved domain version; `O` means optional and may be absent/unknown. A generated material claim must cite the selected transcript run and exact segment/timestamp, with a locally saved excerpt. User-provided claims may lack a transcript citation only when visibly marked as such. “AI” below means optional provider generation; the Restricted path remains extractive.

| Field | Need / type | Extraction, validation, evidence, inference, confirmation |
| --- | --- | --- |
| `meeting_type` | R / enum | User selects one of five types or `general`; no automatic type inference; saved in each new version. |
| Title | R / string or `Chưa rõ` | Start from saved meeting name; user reviews/edits. An ASR/provider title is only a proposal. |
| Actual meeting date/time | O / timestamp with timezone | `created_at` is recording/import time, not proof of meeting time. User enters/confirms actual time; AI cannot invent it. |
| Project/customer | O / string | User-provided free text; transcript mention may be suggested with citation but requires confirmation. Not a workspace ID. |
| Participants | O / list of plain names/roles | No diarization or speaker identification. Do not derive from voice; only explicit cited introductions or user entry, then confirmation. |
| Objective | O / string | Explicit cited statement or user entry; no inferred objective from meeting title alone. |
| Executive summary | O / list of claim entries | Offline path excerpts; provider may paraphrase selected text with citations. Unsupported claims flagged; user reviews before approval. |
| Discussion topics / key points | O / list of claim entries | Preserve terminology and exact source. Keyword ranking may choose excerpts, not declare agreement. |
| Requirements | O / list of typed claims | `kind`: business, functional, non-functional, business rule, constraint, assumption, change. `formality`: candidate/user-confirmed. AI may suggest a kind from explicit evidence, never approve it. |
| Decisions made | O / list of claims | Explicit agreement is required for a candidate. No inferred choice from alternatives; user confirms decision status. |
| Proposed solutions | O / list of claims | Present approaches as unapproved until an explicit decision is reviewed; preserve alternatives and dependencies. |
| Open questions | O / list of claims | Keep unanswered questions unresolved; do not generate an answer. |
| Risks and blockers | O / list of typed claims | Distinguish risk, blocker, dependency, incident impact and cause certainty; no invented severity or root cause. |
| Proposed action description | O / string per suggestion | Requires a cited follow-up or explicit user entry; never creates a tracked task. |
| Proposed action owner | O / string or `Chưa rõ` | AI may copy an explicit owner from cited words only; user confirms; no inferred assignment from a speaker label. |
| Proposed action deadline | O / date/time or `Chưa rõ` | AI may copy an explicit cited date; user confirms timezone/meaning; no invented deadline. |
| Action confirmation status | R if action exists / enum | Starts as suggestion/unconfirmed; author review is separate from future task management. |
| Next steps | O / list of claims | Distinguish recommended follow-up from commitment; cite explicit text or mark user-provided. |
| Evidence references | R for generated material claims / list | `run_id`, `segment_id`, exact `start`/`end`, saved excerpt. Validate against selected working run at creation; compare later edits and flag drift. A valid ID is provenance, not proof of truth. |
| Claim review state and version provenance | R / enums | Claim starts `needs_review`; author confirms/rejects. Manifest retains unverified/approved, origin, parent and source origin. Author approval is not customer sign-off. |

The MVP does not require every optional section to be populated. Unsupported values remain `Chưa rõ`, `Cần xác nhận`, or an empty section as appropriate. It does not assign a numerical confidence score to provider output.

### Generation and evidence policy

- **Offline:** Copy cited excerpts into candidate sections only where explicit wording supports a classification. A keyword hit is a retrieval hint, not proof of a decision, requirement, cause, or assignment.
- **Provider:** Permit Vietnamese paraphrase of reviewed selected segments, but retain exact technical tokens and source IDs. Normalize foreign or missing citations as unsupported; never promote an unsupported claim to a confirmed fact.
- **Traceability:** Segment ID and timestamp provide navigation; the saved excerpt records what the working transcript said when the version was created. Compare it with current working text to detect drift. No citation alone establishes semantic correctness.
- **Coverage:** A review screen may count generated material claims with valid sources versus all generated material claims. The count is a completeness aid, not a confidence score or automatic approval. Unsupported and user-provided claims remain visibly separate; the reviewer must resolve them before approving a new domain version.
- **Human control:** Keep proposals apart from agreed decisions, discussion apart from formal requirements, suspected apart from confirmed incident causes, and UAT observations apart from customer acceptance. Missing owner/deadline stays unknown. The author may approve an internally reviewed version; the product does not claim customer approval.

## 5. Scope and traceability

**MVP:** one domain schema, five type profiles plus general, conservative offline/provider candidates, per-claim source/review, metadata, compatible versioning, bilingual review UI, and truthful Markdown export. **Post-MVP:** organization templates, stronger requirement extraction, cross-meeting decision/context reuse, and optional approved local semantic models. **Future:** Jira/requirements-system integrations, autonomous task tracking, knowledge assistant, shared workspaces, self-hosted sync, and team approval flows. Independent action tasks and local projects already have separate OpenSpec changes; do not absorb their implementation here.

| New requirement | Existing baseline | Acceptance scenario in spec | Implementation task(s) |
| --- | --- | --- | --- |
| ITM-01 | FR-20/21 | Existing meeting has no domain metadata; User identifies a customer meeting | 1.1, 1.4, 3.1, 3.2 |
| ITM-02 | FR-20/23 | Meeting has only topics and questions | 1.1, 2.1, 3.2, 4.1 |
| ITM-03 | FR-22/23, AT-09 | Requirement gathering contains a constraint and an assumption; Technical suggestion sounds like a requirement | 2.1, 2.3, 3.2 |
| ITM-04 | FR-22/23, AT-09 | Architecture alternatives are discussed; Decision is explicit | 2.1, 2.3, 3.2 |
| ITM-05 | FR-20/22 | Status meeting reports a blocker; Incident cause remains suspected | 2.1, 3.2, 4.1 |
| ITM-06 | FR-20/22 | Customer reports a defect during UAT | 2.2, 3.2, 4.1 |
| ITM-07 | FR-22, AT-09; G4 boundary | Follow-up has no owner or deadline | 2.2, 3.2, 4.1 |
| ITM-08 | FR-23, AT-09 | Open a cited claim; Transcript text changes after drafting; Provider returns an unsupported citation | 1.2, 2.3, 3.3 |
| ITM-09 | FR-24/25, PR-01/04, AT-05–08 | Restricted offline draft; Provider draft | 2.3, 2.4 |
| ITM-10 | FR-21/36 | Regenerate after approval; Export a freeform edit | 1.3, 3.1, 3.3, 4.1 |
| ITM-11 | FR-21/34, AT-08 | Existing M3 minutes are reopened; New version save fails | 1.3, 1.4, 4.2 |

Task 4.3 integrates ITM-01–11 across all five types. This table maps planned acceptance, not completed tests.

## 6. Quality gates, risks, and decisions

| Gate | Status on this analysis | Evidence needed to pass |
| --- | --- | --- |
| G0 — Current state verification | Evidence collected; analysis complete | Repository anchors above, OpenSpec inventory, and explicit unknowns. This is a code review, not a live-product acceptance. |
| G1 — Domain scope approval | Pending product-owner review | Confirm five types, terminology, optional metadata, MVP boundaries, and internal approval versus customer sign-off. |
| G2 — Specification completeness | Automated syntax validation passed; human review pending | `openspec validate meeting-minutes-it-customer-domain --strict` passes; reviewer checks negative and positive scenarios and traceability. |
| G3 — Design consistency | Drafted; review pending | Architecture review of version shape, exact source validation, provider payload scope, old-version compatibility, and rollback. |
| G4 — Implementation readiness | Checklist drafted; approval pending | Review task dependencies and fixtures, then approve implementation scope. No application code has been changed. |

**Risks/assumptions:** Keyword extraction can misclassify a phrase, so offline output stays extractive and tentative. Provider citations may be valid but semantically false, so every generated claim remains unverified until reviewed. A working transcript can change, so new versions snapshot cited excerpts. Existing generic minutes remain readable; older app builds may omit new domain sections after rollback. Meeting `created_at` is a storage event, not necessarily the actual meeting date. Customer sign-off, project registry IDs, external integrations, and task lifecycle are separate scopes.

**Unresolved product decisions for G1:** Confirm whether the five named types and the `general` fallback are the intended first release; confirm that “approved” means author-reviewed minutes only, with customer sign-off handled outside FAHMM for this MVP. These decisions are surfaced for review and are not recorded as approved.

## 7. Recommended implementation order

1. Land domain data validation, exact citations, excerpt snapshots, and old-version tests (tasks 1.1–1.4).
2. Add conservative offline and provider candidate generation with privacy tests (tasks 2.1–2.5).
3. Add bridge and bilingual claim-review UI with source navigation (tasks 3.1–3.4).
4. Align preview/export and complete cross-type regression and human review (tasks 4.1–4.3).

Do not infer G1 approval or implementation authorization from this plan.
