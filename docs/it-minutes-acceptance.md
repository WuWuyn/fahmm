# IT customer minutes controlled acceptance

## Run record

- Date: 2026-11-17 (Asia/Bangkok)
- Implementation commit: `39a9b3b` (`feat(minutes): add IT customer domain drafts and review`)
- Branch: `codex/meeting-minutes-it-domain`
- Environment: Windows NT 10.0.26200.0, Python 3.13.7, Node 24.22.1, Rust 1.97.1; offline dependency caches
- Reviewer: Codex, automated fixture and source review
- Data: synthetic Vietnamese and Vietnamese/English utterances created for this repository; no customer recordings or customer content

## Controlled scenarios

`tests/test_minutes_domain_e2e.py` runs one local flow for each customer-facing meeting type. Every case creates a transcript run, generates an offline draft, checks the exact saved source excerpt and absence of drift, corrects one claim, reviews every generated claim, approves the new version, reopens it from a fresh store instance, and exports Markdown. It checks that the predecessor remains unverified and the exported version contains the correction and source text.

| Meeting type | Synthetic input | Guard checked |
| --- | --- | --- |
| Requirement gathering | Customer requests an API CSV export | No generated user-confirmed formal requirement |
| Technical discussion | API v2 and option B are considered without agreement | No invented decision |
| Project status | API milestone is reported at 70% | No assigned or tracked task |
| Issue/incident | Database timeout is suspected as the cause | No confirmed root cause |
| UAT/customer feedback | A login UAT scenario fails | No customer-confirmed acceptance |

All five cases passed. They require an unknown value to render as `Chưa rõ`, forbid task IDs in generated claims, and require the export's action-suggestion caveat. `tests/test_meeting_export.py` separately checks an unknown action owner. The broader suite covers malformed/foreign citations, changed transcript text, provider overclaiming, privacy authorization, legacy minutes, and atomic version behavior.

## Checks

| Check | Result |
| --- | --- |
| `uv run --locked --offline pytest -q` | 208 passed, 4 skipped |
| `npm test -- --run` in `desktop/` | 9 files, 32 tests passed |
| `npm run build` in `desktop/` | Passed; Vite reported a large-bundle advisory |
| `cargo test --offline --manifest-path desktop/src-tauri/Cargo.toml` | 9 passed |
| Ruff check and format on changed Python files | Passed |
| `openspec validate meeting-minutes-it-customer-domain --strict` | Passed |

This is controlled acceptance with synthetic transcript fixtures and automated desktop component tests. It does not establish real-meeting audio quality, manual Windows UI acceptance, or customer sign-off; those belong to their separate release gates.
