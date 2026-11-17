# Design

## Context

See [proposal.md](proposal.md) for the domain motivation and [the spec](specs/it-customer-minutes/spec.md) for observable behavior. Today `MinutesStore` saves an immutable content file and a manifest per version; the manifest records run, origin, parent, source origin, and review state. `OfflineMinutesService` selects excerpts and matches a few decision/action/question words; `normalize_provider_minutes` handles only generic sections. `render_minutes` renders fixed sections, or `user_text` instead of those sections. The transcript's `original.json` is immutable, but `working.json` can change after a minutes version is saved. `CloudMinutesService` already gates provider sends on a reviewed selection and per-send authorization. No main OpenSpec specs are installed yet; the M3 change spec remains the baseline for generic minutes.

## Goals / Non-Goals

**Goals:** Introduce a compatible structured domain layer; keep evidence and review state at the level of each material claim; preserve the M3 privacy and version boundaries; let type-specific views use the same storage model and renderer; keep old versions readable without migration.

**Non-Goals:** Semantic offline summarization without a local model; automatic factual verification; speaker identity; a customer-signature workflow; independent action tasks; cross-meeting/project context; new provider transports or file formats.

## Decisions

### 1. Add a versioned domain payload inside new minutes content

New versions contain `domain_schema_version: 1` and a `domain` object. The object holds `meeting_type`, meeting metadata, common sections, and optional type-specific entries. Old versions keep their existing top-level `title`, `date`, `attendees`, `summary`, `topics`, `decisions`, `actions`, and `open_questions` shape. The renderer and editor branch on `domain_schema_version`; they do not rewrite old content. The existing minutes manifest retains its origin/parent/review fields and the atomic version-directory commit. A new version references exactly one transcript run.

Metadata uses `title`, `meeting_datetime`, `project_customer`, `participants` (plain names/roles, not speaker IDs), and `objective`. Each field has a `value` and provenance (`user_provided`, `source_supported`, or `unknown`); a source-supported value also has citations. `MeetingStore.created_at` is displayed separately as the recording/import timestamp and never silently becomes the actual meeting time. `project_customer` is free text, not a project entity owned by `local-project-workspaces-search`.

Alternative: mutate meeting-level metadata and render several unrelated templates. That would make older minutes change when metadata is edited and produce incompatible schemas for different meeting types.

### 2. Reuse one claim shape and vary only the classification

A material entry has stable `item_id`, `text`, `sources`, `origin` (`extractive`, `provider`, `user_provided`), and `review_status` (`needs_review`, `confirmed`, `rejected`). Requirement entries add `kind` (business, functional, non-functional, business rule, constraint, assumption, change) and `formality` (candidate or user-confirmed). Decision entries remain candidates until source agreement and human review are both present. Proposals are never rendered under decisions. Cause entries use `suspected` or `confirmed`; UAT observations keep an acceptance state separate from observed test results. Action entries keep proposed owner/deadline and `confirmation_status`, but no task ID or task workflow. Empty optional sections are omitted from the document instead of filled with synthetic prose.

An author may confirm or correct a claim and save a new unverified version. Whole-version approval requires review or exclusion of each material generated claim and is an internal document state, not evidence of customer sign-off. Changing the selected type creates a new version rather than relabeling a previously approved one.

Alternative: a single freeform Markdown field is easy to edit but cannot reliably attach type, certainty, or citations to an individual statement. The legacy freeform path remains readable and labeled.

### 3. Snapshot evidence text and detect drift

Every generated claim source retains the existing `{run_id, segment_id, start, end}` reference plus an `excerpt` copied from the selected run's working text when the version is created. New-domain validation checks that the run and segment exist, the timestamps match that segment, and the excerpt belongs to the reviewed input. When `working.json` later differs, the UI shows the saved excerpt alongside current text and marks the claim for re-review. A citation establishes provenance, not semantic truth. Claims supplied by a user without a transcript citation are clearly marked `user_provided` and require user confirmation.

The excerpt is stored only in the local minutes version. Cloud preview includes only the explicitly selected reviewed transcript and prompt; it does not automatically include other meeting metadata, excerpts, or old versions. For legacy versions with no excerpt, the UI retains their timestamp links and labels source-text snapshot availability as unknown.

Alternative: retain only segment IDs. That loses the exact edited text that supported an older draft after transcript corrections. Persisting an entire transcript snapshot per minutes version would be heavier than the cited excerpts required for review.

### 4. Generate candidates conservatively through existing paths

Offline generation remains deterministic and extractive. It can lift directly quoted content into topics and type-specific candidate sections when explicit language supports a classification; otherwise it leaves the content as a topic or open question. It does not paraphrase into a formal requirement, decision, cause, owner, deadline, or acceptance. Provider generation can produce richer Vietnamese wording from selected reviewed segments, but normalization rejects foreign segment IDs, marks all generated claims for review, and leaves any unsupported fact unknown or flagged. Both paths preserve technical terms such as API names, version numbers, and English product names.

The existing Restricted/Cloud permitted state machine and single-use disclosure authorization remain unchanged. New domain metadata is not silently added to a provider request. Any change to bridge payloads must update `desktop/protocol/contract.json`, Python and Rust checks, frontend types, and fixtures together.

Alternative: use a new semantic model by default or trust provider citations as fact checks. Both exceed the current privacy and reliability contract.

### 5. Review and export the saved version, not a transient draft

Extend the Meetings minutes panel with a type selector, concise metadata form, type-relevant sections, claim review controls, citation seek, and a source-drift indication. Keep English/Vietnamese UI translation and Vietnamese default minutes headings. Render and export from the same saved version with review state, origin, section labels, certainty, and per-claim citations. If an author uses freeform Markdown, keep its underlying citations in a clearly separate appendix and never say they verify every edited sentence. Do not create an action task from a minutes suggestion in this change.

Alternative: generate a separate export document model. That risks the preview and exported claim/status differing and duplicates source logic.

## Risks / Trade-offs

- **Heuristic false positives** → Keep uncertain text as discussion or a candidate, require source and human review, and test negative examples for every meeting type.
- **A valid citation does not prove the generated claim** → Preserve excerpt and current transcript comparison, keep provider output unverified, and require claim review before approval.
- **Older app cannot show new domain sections after rollback** → Keep old files untouched and document that rollback preserves new files but may render only generic content; restore the new app to review them.
- **More sections increase review burden** → Use one common schema, collapse empty/irrelevant sections, and avoid a required value for optional sections.
- **Quoted excerpts duplicate sensitive content** → Store only cited excerpts in the existing local meeting directory and apply the same deletion/privacy policy as minutes.
- **Long transcript or provider output blocks review** → Keep work off the visible interaction path and test a representative long transcript through existing job/bridge boundaries before acceptance.

## Migration Plan

1. Add read/render support for `domain_schema_version: 1` while retaining the existing generic renderer and legacy manifest handling. Do not rewrite existing versions or transcript runs.
2. Add new-domain validation and generation behind the selected type. Save each result into a new atomic minutes version; approved predecessors remain unchanged.
3. Update UI/bridge/export together, including protocol fixtures, and verify old generic versions, new versions, failure rollback, and Restricted egress on the same build.
4. On app rollback, preserve the new version files; the older app may omit domain-only sections. Returning to the new app restores their view. No destructive down-migration is planned.

## Open Questions

- Whether a future project registry should replace the free-text `project_customer` field is deferred to `local-project-workspaces-search`.
- Formal customer sign-off, organization-specific templates, and retention rules beyond current local meeting deletion require separate product decisions after this MVP.
