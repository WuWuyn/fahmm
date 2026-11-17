# Tasks

## 1. Domain data and source integrity

- [ ] 1.1 (ITM-01, ITM-02) Add the versioned domain payload and validation for meeting type, metadata provenance, common sections, optional type-specific sections, claim IDs, classifications, and review states; verify round-trip and malformed-field tests for all six meeting types.
- [ ] 1.2 (ITM-08) Validate new claim sources against the selected transcript run's exact segment IDs/timestamps and save cited working-text excerpts; verify foreign IDs, altered times, missing excerpts, and post-draft transcript edits are flagged without changing old versions.
- [ ] 1.3 (ITM-10, ITM-11) Preserve atomic version commits and legacy generic read/select/approve behavior while gating new-domain approval on reviewed claims; verify an interrupted save and a new version after an approved version leave prior bytes and another meeting intact.
- [ ] 1.4 (ITM-01, ITM-11) Document the new version shape, recording/import time versus actual meeting time, rollback limitations, and local excerpt retention in repository documentation; verify the documented examples with a saved-version fixture.

## 2. Conservative draft generation

- [ ] 2.1 (ITM-02, ITM-03, ITM-04, ITM-05) Extend the offline extractive path to emit only cited candidates for common and requirement/technical/status/incident sections; verify positive and negative Vietnamese and mixed-language fixtures, including alternatives with no decision and a suspected cause with no confirmed cause.
- [ ] 2.2 (ITM-06, ITM-07) Add UAT observation/acceptance separation and action-suggestion fields with unknown owner/deadline defaults; verify a failed UAT scenario stays unaccepted and no task ID or assigned-task state is created.
- [ ] 2.3 (ITM-03–ITM-09) Normalize provider output into the same domain payload, reject or flag unselected/invalid citations, and require review for every generated material claim; verify a fake provider cannot turn an unsupported requirement, decision, cause, owner, deadline, or customer acceptance into confirmed data.
- [ ] 2.4 (ITM-09) Preserve the existing Restricted and per-send Cloud permitted policy when generating domain minutes; verify blocked-network offline generation, exact selected-payload preview, cancel/replay denial, and a representative long transcript without UI-thread stalls.
- [ ] 2.5 (ITM-03–ITM-09) Document the difference between extractive candidates, provider drafts, internal author approval, and customer sign-off in the user guide; verify every stated generation limit matches a fixture or privacy test.

## 3. Review interface and bridge

- [ ] 3.1 (ITM-01, ITM-02, ITM-10) Add bounded bridge operations/DTO fields for selecting type, saving domain edits, reading claim review state, and source drift; update `desktop/protocol/contract.json` and Python/Rust/frontend fixtures, then verify invalid IDs, unknown fields, stale versions, and no unmanaged paths are accepted.
- [ ] 3.2 (ITM-01–ITM-07) Add bilingual type selector, metadata fields, common/type-specific sections, claim classification and review controls in the Meetings minutes panel; verify all five customer-facing types and `general` render with empty optional sections suppressed and no auto-confirmed customer facts.
- [ ] 3.3 (ITM-08, ITM-10) Show each saved source excerpt, current transcript difference, and timestamp seek; keep freeform edits visibly distinct from claim-level verification. Verify source seek, drift warning, and unsaved-change/version-switch behavior in UI tests.
- [ ] 3.4 (ITM-01–ITM-10) Update English/Vietnamese labels and the minutes review guide with an end-user walkthrough; verify language switching changes interface copy while the default minutes headings remain Vietnamese and technical terms remain intact.

## 4. Rendering, export, and integrated acceptance

- [ ] 4.1 (ITM-02–ITM-08, ITM-10) Render the new domain payload and Markdown export from the same saved version with section/certainty/review labels, item citations, and the action-suggestion caveat; verify preview/export equivalence, `Chưa rõ` fields, and a freeform edited version's separate underlying-reference notice.
- [ ] 4.2 (ITM-10, ITM-11) Verify legacy generic minutes still render/export unchanged, new versions do not rewrite prior approved files or ASR artifacts, and write failure leaves the last committed version readable; record fixture hashes before/after.
- [ ] 4.3 (ITM-01–ITM-11) Run a controlled end-to-end set for all five meeting types using licensed/consented Vietnamese and mixed-language transcript fixtures: review sources, correct one claim, approve, reopen, export, and confirm no unsupported decision, formal requirement, confirmed root cause, UAT acceptance, or tracked task appears. Record environment, commit, results, and reviewer; keep customer content out of Git.

## Workflow follow-up

- Review G1 domain scope with the product owner before application-code implementation.
- Archive this change only after implementation evidence and the repository's review gates are satisfied.
