# PR review checklist — Flow 1/2 and architecture

Use this form in every implementation PR after adopting the proposed gate policy. Do not confuse it with an already installed GitHub branch-protection rule.

## Scope

- PR title and link:
- Base commit / head commit:
- Affected gates (G0–G6):
- Linked OpenSpec change:
- Linked requirement IDs (FR/AT, and spec/scenario):
- Product claim in scope:

## Required code review questions

- [ ] Does the change have an explicit user-visible behavior and acceptance scenario?
- [ ] Is the source of truth still Python for recording, transcript, minutes, local storage and privacy?
- [ ] Are any new bridge operations reflected in desktop/protocol/contract.json and TS/Rust/Python types/validation/tests?
- [ ] Are unsupported operations, invalid identifiers, stale versions and malformed payloads rejected?
- [ ] Are native OS paths, API keys and confidential media excluded from the webview and ordinary diagnostics?
- [ ] Does Restricted mode remain strictly offline under direct bridge calls and failed-network/provider conditions?
- [ ] Are data writes atomic, and are previously approved minutes, original transcripts and unrelated meetings preserved?
- [ ] If ASR/model/provider work is long-running, can users still inspect status and cancel/retry safely?
- [ ] Are new action items clearly marked candidate until user review? If task storage changes, is an old-meeting migration test included?
- [ ] Are frontend, Rust, Python and manual regression checks recorded for the relevant gate?
- [ ] Is a new hardware acceptance result needed because recording/pause/recovery behavior changed?
- [ ] Does product copy avoid “local semantic AI,” “managed tasks,” “workspace,” “sync” or “speaker identity” claims that the code does not yet fulfill?
- [ ] Are failures, data-loss and privacy-negative tests included—not only happy-path tests?

## Suggested regression commands (run in the actual repository)

On Windows with the project's pinned toolchains:

Repository root:

    uv run --locked --extra legacy-qt pytest -q
    uv run --locked ruff check .
    uv run --locked ruff format --check .
    openspec validate flow12-quality-gates --strict

From desktop/:

    npm ci
    npm test -- --run
    npm run build

From desktop/src-tauri/:

    cargo test --lib

These are proposed run commands based on existing verification docs, not execution results. Check the repository's actual lockfiles, platform notes and newest build instructions before running; do not treat Windows-only hardware tests as runnable on Linux CI.

## Approval

| Area | Reviewer | Evidence link | Result |
| --- | --- | --- | --- |
| Contract/automated tests | | | |
| Privacy/security | | | |
| Data integrity | | | |
| Manual hardware, if impacted | | | |
| Product scope and wording | | | |

**Release note:** State what can now be claimed and what remains unverified. A merged PR is not the same as a signed-off acceptance gate.
