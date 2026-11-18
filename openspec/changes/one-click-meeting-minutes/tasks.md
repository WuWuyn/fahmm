# Tasks

## 1. Universal draft content and persistence

- [x] 1.1 Extend the existing offline domain extractor for `general` to populate the universal sections conservatively, with exact working-text citations, unknown owner/deadline defaults, proposal/decision separation, and within-section deduplication; verify focused Vietnamese and mixed-language service tests.
- [x] 1.2 Select bounded chronological discussion coverage for long transcripts and add a representative IT/customer fixture spanning early, middle, and late meeting periods; verify the one-hour fixture yields cited coverage across all three periods without duplicate claims.
- [x] 1.3 Keep existing domain validation and atomic version storage for the new draft, including blank transcript, failed commit, and approved-version preservation; verify service/store regression tests and the existing malformed-provider-output tests.

## 2. One-click desktop workflow

- [x] 2.1 Replace the primary creation controls with one Generate meeting minutes action that uses the active transcript and fixed universal type; keep any specialized or provider flow secondary. Verify missing/blank transcript, working/duplicate-request, success auto-open, and failure/retry states in UI tests.
- [x] 2.2 Guard unsaved edits during regeneration, keep prior versions selectable, and show every universal section including empty sections in review and Markdown export; verify edit/reopen, source seek, regeneration, and export tests.
- [x] 2.3 Add English/Vietnamese action, state, and recovery copy, and document the exact user journey and extractive-versus-provider boundary; verify language tests and the walkthrough against the implemented controls.

## 3. Integrated acceptance

- [x] 3.1 Run OpenSpec strict validation, focused Python/React/Rust checks, and a bridge-to-export smoke test with a saved transcript; record actual results and limitations in `docs/traceability-map.md` without claiming live 60-minute AI accuracy or clean-machine release acceptance.

## Workflow follow-up

- Archive only after the repository's review and release gates are satisfied.
