# Design: executable quality gates around a local-first core

## Context

Current observed architecture:

1. **Presentation:** React/TypeScript features render recording, meetings/transcript, minutes, models and settings; UI invokes the typed bridge client.
2. **Desktop host:** Tauri/Rust owns native import/export dialogs, short-lived playback media access and Python sidecar lifecycle.
3. **Authority:** Python bridge validates operations and dispatches to recording, ASR, transcript, minutes, provider/privacy and storage services.
4. **Persistence:** managed local per-meeting data; original/working transcript runs and versioned minutes.
5. **External egress:** an explicitly authorized provider operation after an exact user-reviewed snapshot; never an automatic fallback from offline processing.

The protocol is versioned JSON-lines IPC, not a localhost HTTP server. Keep recording data and secrets inaccessible to the webview through arbitrary file paths. The GitHub code and historical evidence at the pinned commit are the audit baseline, not a newly executed test run.

## Decisions

### D1 — Separate implementation state from acceptance state

Every gate has an outcome:

| State | Definition |
| --- | --- |
| NOT_IMPLEMENTED | Required behavior or data contract does not exist. |
| IMPLEMENTED_UNVERIFIED | Code exists, but no attributable passing verification. |
| AUTOMATED_VERIFIED | Required automated checks passed on the specified commit and environment. |
| MANUAL_VERIFIED | Real-hardware or representative manual checks passed and were recorded. |
| ACCEPTED | All applicable mandatory checks passed, dependencies accepted and reviewer signed off. |
| BLOCKED | A prerequisite, test failure, missing permission or missing evidence prevents acceptance. |

States are evidence-derived, not a single monotonic progress percentage. A new commit touching the behavior invalidates stale gate claims until relevant tests are rerun; historic evidence remains archived. A gate can have automated evidence yet be BLOCKED for manual acceptance.

### D2 — Define gate dependencies

| Gate | Acceptance domain | Prerequisites |
| --- | --- | --- |
| G0 | Build, versioned bridge, source of truth, safety regression | No feature dependency; required again for every release candidate. |
| G1 | Real Windows dual-source record / pause / crash recovery | G0 and permitted meeting hardware. |
| G2 | Import / offline ASR / transcript review / seek | G0; may be independently tested with controlled imported audio. |
| G3 | Offline minutes / versioned review / Restricted and confirmed provider sharing | G0 and G2's source/run contract. |
| G4 | Independently persisted action item review / status / ownership / provenance | New approved scope plus G3 source/version contract. |
| G5 | Real meeting → transcript → minutes → tracked actions end to end | G0, G1, G2, G3, G4 accepted. |
| G6 | Portable/installer release on clean Win10/Win11 | G0–G3 and M4 release checks; G4 required only if advertised in that release. |

**Scoping rule:** It is valid to accept a narrower v1 journey ending at a reviewed minutes document with an action-suggestions section (G0–G3 plus real-world G1), while G4 remains not implemented. It is invalid to label that narrower scope “independent action item management.”

### D3 — Evidence format and review policy

Every acceptance record identifies full commit SHA, OS/build, app package hash where applicable, model/revision, test procedure or command, actual result and exit code, expected behavior, negative tests, evidence file/hash, reviewer and date. Sensitive recordings/transcripts, API keys and provider payloads must not be copied into public artifacts.

Test layers:

- **Service/contract:** unit, bridge-failure, malformed frames, privacy bypass attempts.
- **Integration:** cross-process frozen sidecar, real ASR worker, persisted reopen, Tauri audio/player path.
- **Hardware:** permitted 20-minute Teams/Meet loopback + mic capture, audibility, Pause/Resume, kill and recover.
- **Release:** package on clean supported machines, offline model use, local data retention, redistribution review.

Human sign-off is mandatory where acceptance involves audible sound, user consent or semantically meaningful review. Prior docs may seed a checklist but do not create an automatic pass on a new build.

### D4 — Keep domain authority in Python while strengthening boundaries

Current path for a user action:

    React feature → shared bridge client → Rust named command
                 → supervised Python sidecar → domain service
                 → managed per-meeting storage

Only the cloud-minutes service, after its policy and confirmation checks, may send selected content to a configured provider. UI state is never sufficient authorization. Rust owns import/export user dialogs and grants scoped playback tickets, not general filesystem permissions. Every new operation requires contract entry, shared DTO/fixtures, Python runtime validation, Rust allowlisting, frontend type/UX handling and negative tests.

Observed design risk: Rust call_backend holds the backend-state Mutex guard during a potentially long sidecar call. Measure whether a synchronous provider operation delays unrelated commands. If reproduced, shorten lock ownership and use a request-multiplexed supervisor or background job, preserving mutation ordering and explicit cancellation. Do not refactor solely on speculation.

Observed maintenance tradeoff: Python bridge/server.py is a large operation dispatcher. Extract domain handlers incrementally (recording, transcription, minutes, library/tasks) only with byte-for-byte contract regression tests.

### D5 — Preserve provenance and immutable approvals

Current logical identities:

- Meeting ID owns recordings, transcript runs and minutes versions.
- Transcript run has immutable original and editable working content; source segment IDs and timestamps link derived facts.
- Minutes versions preserve source references and an approval state; new generations must not overwrite approved versions. New edited versions retain an immediate `parent_version_id` and the original extractive or provider `source_origin`. Legacy edited versions with no recoverable origin must be labeled unknown rather than assigned a guessed source.

Proposed **future** action item entity (not current code):

| Field | Proposed rule |
| --- | --- |
| action_id | Stable generated ID independent of the minutes version. |
| meeting_id | Required owning meeting. |
| description | Editable user-confirmed task. |
| status | Candidate / open / in_progress / done / cancelled, with validated transitions. |
| owner | Optional local display value; unknown stays unknown. No team account requirement. |
| due_date | Optional date with explicit timezone/date-only semantics; never invented from text. |
| source_refs | Transcript run + segment ID/timestamps and creating minutes version ID. |
| review_state / revision | Auditable acceptance and optimistic concurrency token; append or retain revisions. |

Extraction creates **candidates**, not confirmed assignments. Explicit user approval promotes candidate tasks. Subsequent transcript/minutes edits never silently mutate an approved action. If the source version is deleted, keep or tombstone provenance according to separately specified retention rules. Specify exports and migration before shipping.

### D6 — Sequence future architecture deliberately

1. Stabilize G0–G3 and G1 real-device acceptance without a broad rewrite.
2. If full Flow 2 is intended, implement G4 task store/service/protocol/UI as a separate OpenSpec change, with migration and deletion tests.
3. For Flow 3, introduce meeting/workspace grouping, full-text search and cross-meeting context with explicit scoping. A rebuildable local SQLite FTS index is a possible design, **not an adopted choice**; per-meeting files stay authoritative until migration is agreed.
4. For Flow 4, add diarization as distinguishable anonymous speaker segments first; do not imply identity recognition. Plugin SDK and external integrations require sandbox, permissions, versioning and per-integration egress review.
5. For Flow 5, design identities, consent, encryption, conflict resolution, offline-first sync and multi-tenant access controls before any mobile/team server implementation.

Defer migrations, plugins, sync and cross-meeting AI retrieval until their own goals, threat models, tests and acceptance cases are approved.

## Risks and Trade-offs

- **Hardware variability:** controlled adapters cannot establish WASAPI audibility. The gate requires replay/listen evidence, not only nonzero RMS.
- **Privacy regression:** new provider, search or plugin paths can bypass UI prompts. Service-level egress denial and network-blocking tests are mandatory.
- **Over-scoping v1:** requiring a local semantic LLM, task management, diarization or sync would change product scope. Record these as future proposals unless explicitly approved.
- **Performance:** long synchronous calls, large audio files and many meetings need bounded payloads, background work and focused regression tests.
- **Evidence drift:** a checked implementation task, old test log or unversioned manual note is not an up-to-date release acceptance record.
