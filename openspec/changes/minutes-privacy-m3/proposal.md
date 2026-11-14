# Proposal

## Why

M2 can produce and review a local transcript, but the user cannot yet turn it into useful meeting minutes. M3 completes that step while enforcing the v1 promise that restricted meeting content stays on the device and any cloud disclosure is deliberate.

## What Changes

- Add a Vietnamese, source-linked offline extractive minutes draft that works with no internet, account, API key, GPU, or local LLM. Label it unverified and make its limits explicit.
- Add local minutes versions with review, editing, source navigation, regeneration, and preservation of an approved version.
- Add a persistent per-meeting Internal/Restricted or Cloud permitted classification and a single, auditable decision point before each cloud request. Never send audio or silently fall back from local work to a provider.
- Add multiple OpenAI-compatible provider profiles, Windows-protected API keys, editable prompt/template settings, a payload preview, and retryable provider errors.
- Exercise AT-05 through AT-09, including blocked-network and negative egress checks. Keep M1 real-meeting acceptance and M4 export, deletion, and packaging in their own milestones.

## Capabilities

### New Capabilities

- `meeting-minutes`: Offline draft content, source citations, review, editing, regeneration, and approval of local minutes versions.
- `meeting-privacy`: Meeting classification and enforceable controls on sending meeting content outside the device.
- `provider-profiles`: Configuration and secure storage of OpenAI-compatible provider profiles.
- `cloud-minutes`: Explicitly authorized provider requests and normalization of their Vietnamese minutes responses.

### Modified Capabilities

None. The project has no main OpenSpec specs yet; M1 and M2 behavior is described in their change specs and the v1 requirements.

## Impact

The Meetings screen gains privacy mode, offline draft, source-linked minutes review, and cloud confirmation controls. Settings gains provider profiles. M3 reads M2's working transcript and extends per-meeting local storage for minutes versions and review state. The implementation adds the OpenAI Python SDK and a Windows credential-store integration; provider calls remain optional and are isolated from recording, import, local ASR, and offline drafting. No backend, account, export format, or local LLM is introduced by M3.
