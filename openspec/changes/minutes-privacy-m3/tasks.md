# Tasks

## 1. Meeting state and minutes storage

- [x] 1.1 Add a validated per-meeting privacy-mode operation to `MeetingStore`/`MeetingLibrary`, treating missing or invalid modes as Restricted; verify new, v1, and v2 meetings plus restart and provider-error persistence in storage tests.
- [x] 1.2 Add atomic per-meeting minutes versions with origin, transcript run, source references, review state, active version, and immutable approved content; verify interrupted writes, edit/regeneration, and rollback-friendly reads in store tests.
- [x] 1.3 Document the optional metadata fields and `minutes/` layout in the storage migration guide; verify an M2 meeting can be reopened with its transcript unchanged.

## 2. Offline Vietnamese minutes

- [x] 2.1 Implement deterministic extraction from the selected run's edited segments into the standard Vietnamese minutes sections, preserving source IDs and timestamps; verify blank transcript, topics, explicit decisions/actions, and `Chưa rõ` fields with focused tests.
- [x] 2.2 Add editable local template/guidance and new-version regeneration without provider initialization; verify offline operation with sockets blocked and no API key, plus preservation of an approved version.
- [x] 2.3 Document the extractive draft's limits and source-link behavior in an English user guide; verify its steps against a generated or imported test meeting.

## 3. Provider profiles and protected secrets

- [x] 3.1 Add the OpenAI Python SDK dependency and a Windows Credential Manager adapter that fails closed when unavailable; verify an actual Windows credential round trip and tests proving no plaintext key reaches profile, meeting, or log files.
- [x] 3.2 Implement multi-profile local settings and URL validation (HTTPS with TLS verification; HTTP only for explicit loopback; unsafe redirects rejected); verify persistence, profile removal/key deletion, malformed URL rejection, and no-provider offline use.
- [x] 3.3 Add provider profile editing to the existing Settings screen with name, Base URL, model, timeout, and masked key controls; verify create/edit/select/delete and restart in Qt tests, and document configuration and cost disclosure.

## 4. Cloud request and privacy enforcement

- [x] 4.1 Build an immutable request snapshot from only user-selected, reviewed working segments and the chosen prompt/token limit; verify the preview lists destination, data types, and exact outgoing content while omitting audio, other runs, local paths, and keys.
- [x] 4.2 Implement the single-use per-send disclosure authorization and transport-boundary mode recheck; verify direct service calls in Restricted mode, cancel, changed mode/profile/payload, retry, and regeneration produce zero unauthorized content egress with socket spies.
- [x] 4.3 Implement the optional OpenAI-compatible chat-completions transport with timeouts, safe error mapping, and no local fallback to cloud; verify a loopback text-only provider, quota/timeout/network failures, key redaction, and preservation of audio/transcripts/minutes.
- [x] 4.4 Normalize provider output into unverified Vietnamese minutes, validate source IDs against the selected segments, and default unsupported owner/deadline/attendee/decision fields to `Chưa rõ`; verify text/structured responses, invalid citations, and AT-09 fixtures.
- [x] 4.5 Document the data-flow boundary, confirmation semantics, and endpoint policy in an English privacy guide; verify the described Restricted and Cloud permitted paths with the service tests.

## 5. Meeting review workflow

- [x] 5.1 Add privacy classification and offline draft controls inside Meetings, with an unverified label, editable minutes, version selector, approval action, and transcript/audio citation navigation; verify an imported and a recorded meeting can save, reopen, edit, and regenerate without losing an approved version.
- [x] 5.2 Add selected-segment controls, provider/template/token selection, a full disclosure preview, and explicit Confirm/Cancel before cloud generation; verify Restricted controls and direct gate, cancel, confirmed send, and retry in Qt tests.
- [x] 5.3 Keep generation off the Qt UI thread, show retryable provider errors without exposing secrets, and document the complete M3 user flow; verify responsive navigation and persisted review state after restart.

## 6. Integration acceptance

- [x] 6.1 Exercise AT-05 with a controlled, consented or generated recording/transcript while external sockets are blocked: local recording, ASR, and offline draft complete with no meeting-content egress; record evidence and distinguish it from pending M1 real-meeting hardware checks.
- [x] 6.2 Exercise AT-06 through AT-08 against a loopback provider and socket spy: Restricted attempts send nothing, Cloud permitted sends only after each confirmed preview, and provider failures preserve local data; record host/payload and retry evidence without secrets.
- [x] 6.3 Exercise AT-09 with missing owner/deadline and source-linked decision fixtures; verify `Chưa rõ`, valid timestamps, and review flags, then record the result and any semantic-verification limitation.
- [x] 6.4 Run the complete M1–M3 automated suite, Windows app smoke flow, lint, and strict OpenSpec validation; update project status with results while leaving M1 real-meeting and M4 release acceptance pending.
