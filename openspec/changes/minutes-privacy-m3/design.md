# Design

## Context

See [proposal.md](proposal.md) for motivation and the four capability specs for observable behavior. M2 stores each meeting under `%LOCALAPPDATA%/fahmm/meetings/<id>`, with `metadata.json` schema v2 and versioned `transcripts/<run-id>/original.json` and `working.json`. `TranscriptStore.active_run()` exposes the current edited segments; `MeetingsPage` already provides segment selection and playback. New meetings have `privacy_mode: restricted`, but the mode is not editable or enforced at a cloud boundary yet. The Settings page is a placeholder. There is no required server or database.

## Goals / Non-Goals

**Goals:**

- Make the reviewed working transcript the only input for minutes, with stable run/segment references.
- Keep offline generation callable without provider configuration, secrets, or network initialization.
- Make one policy boundary responsible for every request carrying meeting content, including retries and non-UI calls.
- Preserve previously approved minutes and existing M1/M2 data when an operation fails.

**Non-Goals:**

- A local LLM, background cloud processing, automatic semantic fact verification, or a promise that extractive drafts read like a human summary.
- M4 Markdown/TXT export, meeting deletion, packaging, and approval of internal infrastructure as safe for Restricted content.
- Completing M1's real Teams/Meet hardware acceptance without a permitted meeting.

## Decisions

### 1. Per-meeting minutes versions on the filesystem

Add `minutes/<version-id>/manifest.json` and `content.json` for each generated or edited version. The content contains the structured Vietnamese fields, source references as `{run_id, segment_id, start, end}`, and user-edited text; the manifest records origin (`extractive` or `provider`), creation time, template revision, review state, and provider identity without credentials or sent transcript text. Write into a staging directory, flush, then atomically rename, following M2's transcript pattern. Store `active_minutes_version` as an optional metadata v2 key, so existing meetings need no eager migration. Editing or regenerating an approved version creates a new unverified version; approval marks a saved version and never overwrites its content. Older app versions can ignore the new directory and optional metadata field.

Alternative: one mutable `minutes.md` file would be simpler but could destroy an approved result during edit or provider failure and cannot retain stable source links. A database adds migration and deployment cost without a v1 need.

### 2. Deterministic offline extraction, with conservative labels

Build a local extractor over the selected run's `working.json`. Normalize text, skip blank segments, score representative segments for topic coverage using word frequency and position, and preserve their original wording and timestamps. Populate the standard sections from cited excerpts. Only recognize decisions or actions when explicit language is present; leave unsupported fields as `Chưa rõ`. The draft records which segments supplied each item and labels itself “Unverified · Offline extractive draft.” Template edits change headings and guidance for future versions, but cannot turn unsupported claims into inferred facts. Large transcripts are processed off the Qt UI thread.

Alternative: a local LLM could improve prose but adds large model downloads, variable CPU/RAM needs, and unpredictable factual claims. It remains a later optional path.

### 3. Disclosure gate before provider transport

Create a content-egress service that is the only caller of provider transport. It loads the meeting classification from `MeetingStore` (missing/invalid means Restricted), loads only explicitly selected segments of the current edited run, constructs an immutable request snapshot, and displays the destination host, content types, prompt, selected transcript, and token limit. Confirmation yields a single-use authorization bound to meeting ID, provider profile, payload hash, and mode. The service re-reads the mode and consumes the authorization immediately before opening the request; a mode change before that point aborts. It holds the appropriate meeting state lock through the send-start decision so UI and service cannot race at that boundary. Retries and regeneration create a new snapshot and require fresh confirmation. No provider client or connectivity probe is initialized by offline draft generation.

Alternative: disabling the cloud button in Restricted mode is insufficient because background actions and future callers could bypass the UI. A generic network interceptor would also affect user-requested model downloads and cannot distinguish content-bearing calls reliably.

### 4. Optional provider profiles and secret isolation

Save non-secret profile settings in a local user-level JSON file and keep API keys in Windows Credential Manager through a small OS adapter. If protected storage is unavailable, saving a key fails visibly; there is no plaintext fallback. Provider calls use the OpenAI Python SDK with the configured Base URL and chat-completions text response. Validate URL scheme, host, port, and path; allow HTTPS with ordinary certificate verification and HTTP only for an explicit loopback host. Reject redirects that would violate the endpoint policy. Do not log request bodies, responses, API keys, or raw exception messages that may contain them. A profile can omit a key for a local provider, but its use still follows the Cloud permitted gate until a separately approved trusted-local engine exists.

Alternative: environment variables or an encrypted JSON file would complicate desktop use and key lifecycle; a plain settings file violates FR-29. A raw HTTP client would repeat auth, timeout, and compatible API behavior already supplied by the required SDK.

### 5. Normalize provider output before saving

Send a Vietnamese default instruction with stable segment IDs/timestamps and request the standard minutes sections. Accept plain text or structured content, then normalize it into local minutes fields. Validate cited IDs against the selected segment set; reject foreign IDs, default absent owner/deadline/attendee fields to `Chưa rõ`, and flag any claim with missing or invalid evidence for review. No model output becomes approved automatically. The reviewer can inspect a cited transcript segment and audio before approval. Provider work runs off the UI thread and saves a new version only after a valid response; quota, timeout, network, or parse failure leaves existing audio/transcripts/minutes intact.

Alternative: requiring JSON Schema or streaming would reject otherwise OpenAI-compatible endpoints. Trusting model citations or factual claims without local checks would conflict with AT-09; source ID validation cannot prove semantic truth, so the unverified review state remains necessary.

### 6. UI placement and test boundaries

Keep Recorder, Meetings, Models, and Settings as the four top-level screens. Add classification, segment selection, minutes generation/review, source navigation, and disclosure preview within Meetings; add provider profiles within Settings. Use controlled local audio/transcript fixtures and a loopback fake provider for AT-05–AT-09, plus socket blocking/spying to assert zero content egress in Restricted mode and before confirmation. Test the service directly as well as through Qt so privacy does not depend on a button state. Retain the full M1/M2 regression suite.

Alternative: a fifth Minutes page would break FR-38 and fragment the review flow.

## Risks / Trade-offs

- **Extractive draft sounds incomplete** → Label it clearly, keep excerpts and timestamps, and require review before approval.
- **A provider can invent a plausible fact despite a valid citation** → Validate citation IDs and absent fields, mark every provider version unverified, and make source audio one click away; do not claim automatic semantic verification.
- **A provider URL redirects or a profile changes between preview and send** → Bind authorization to the immutable snapshot and profile, validate the effective endpoint, and reject unsafe redirects.
- **Secrets leak through errors or logs** → Centralize transport error mapping, redact exception details, and assert key absence in persisted files and test logs.
- **Partial writes or old metadata** → Use staged atomic saves, optional v2 metadata fields, and fail closed for absent/invalid privacy classification.

## Migration Plan

No eager migration. Existing M1/M2 meetings read as Restricted, keep their transcript runs, and gain `minutes/` only on first draft. Existing metadata v1 handling remains in `MeetingStore`; M3 adds optional fields without changing its schema version. Provider profiles are created only when the user saves one. On rollback to M2, the extra minutes directory and settings are ignored while audio and transcripts remain usable. Do not delete M3 files automatically during rollback.
