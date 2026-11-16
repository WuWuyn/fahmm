# Flow 1/2 review and release gate policy

Engineering owner: the author of the affected code change. Engineering reviewer: a reviewer other than the author for release acceptance; Codex may prepare and self-review test evidence but cannot substitute for the human release decision. Product owner: the user approving the advertised scope. Privacy reviewer: the engineering reviewer of egress, secrets and deletion behavior. The release owner collects records and signs G6 after product and engineering decisions. Record actual names and dates in each gate file before marking `ACCEPTED`.

| Gate | Mandatory evidence before acceptance | Decision owner |
| --- | --- | --- |
| G0 | Same code commit, protocol fixtures, full Python suite and lint, frontend tests/build, Rust tests, negative boundary checks; all required commands exit 0 or have a recorded, approved exception | Engineering reviewer |
| G1 | Permitted live 20-minute dual-source recording, listener assessment of both sources, real pause timing, interrupted-session recovery and unrelated-meeting integrity | Engineering reviewer and product owner |
| G2 | Four-format import; licensed 30-minute offline Vietnamese ASR with model provenance, timestamp/edit/reopen/seek and Cancel/Retry checks; representative speech caveats | Engineering reviewer and product owner |
| G3 | Source-linked extractive/unknown-value review, prior approved version integrity, server-enforced Restricted and exact one-send preview, stale/replay/error tests | Privacy/engineering reviewer and product owner |
| G4 | Only if managed tasks are in release scope: independent task store, explicit promotion, provenance, status/owner/date/revision, restart/deletion/migration and user review | Product owner and engineering reviewer |
| G5 | One authorized representative real meeting through the advertised final output, with G0–G3 accepted and G4 accepted if tracked tasks are advertised | Product owner and engineering reviewer |
| G6 | Packaged artifact and hash, clean Windows 10 and 11 x64, no separately installed Python, offline/privacy smoke, model/dependency redistribution review | Release owner, product owner and engineering reviewer |

## PR and exception rules

1. The PR author lists affected FR/PR/AT rows from `docs/traceability-map.md`, the linked OpenSpec change, changed contract fields and affected gates in `docs/pr-change-control.md` or the PR body. A reviewer verifies that code, fixtures, tests and user-facing claims agree.
2. Every gate record lives under `docs/evidence/`, outside meeting storage. It identifies the full tested code SHA, environment, commands/procedures, actual exit codes, evidence hashes, owner and reviewer. Never include meeting audio, confidential transcript text, provider payloads or API keys.
3. Failed mandatory behavior, missing manual permission/sample, privacy bypass, data loss and absent clean-machine checks remain `BLOCKED` or unaccepted. A historical report or checked task does not waive a current gate.
4. An exception must name the affected requirement, failed check, user impact, mitigation, responsible owner, expiry and approving product/engineering reviewers. It is valid only for a non-critical gate item and only for the stated build. Privacy egress, data integrity, audible dual-source capture for G1 and clean-machine compatibility for G6 cannot be waived while advertising those claims.
5. A code change touching an accepted behavior invalidates that gate's current acceptance until relevant checks are rerun against the changed code commit. Documentation-only evidence commits may reference the exact tested code SHA but cannot turn a failed result into a pass.
6. The release owner may advertise a minutes-only v1 with action suggestions if G4 is excluded explicitly. The product owner's earlier request for a source-linked Action Item Manager establishes development direction; it does not by itself prove G4 acceptance.

Current engineering evidence is `docs/evidence/flow12-g0-2026-11-16.md`. It records passing local automated checks on the current code commit and outstanding skipped/manual checks; G0 has no human release sign-off. The 2026-11-15 record describes the superseded format failure and must not be used to judge the current commit.

The repository's `.github/workflows/quality-gates.yml` runs the Python suite and Ruff lint/format checks, frontend tests/build, Rust host tests, and strict OpenSpec validation on pull requests and pushes to `main`. Pull requests also require FR/PR/AT, G0–G6 and OpenSpec mapping in their body. The Python job publishes skipped tests separately; a skipped real-model or licensed-sample test is not acceptance evidence. CI success is a prerequisite for code integration, not a substitute for G1–G6 manual acceptance or a current G0 evidence record. GitHub branch-protection settings must be verified separately from this file.
