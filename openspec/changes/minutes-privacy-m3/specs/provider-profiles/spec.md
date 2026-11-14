# Spec Delta

## Purpose

Let users configure optional OpenAI-compatible minutes providers without making a provider or API key necessary for local recording, transcription, or offline drafting.

## ADDED Requirements

### Requirement: Multiple optional profiles
The user SHALL be able to create, edit, select, and remove multiple provider profiles with a name, Base URL, Model ID, timeout, and optional API key. The app SHALL retain profiles across restarts without changing any meeting's privacy mode.

#### Scenario: Reopen settings
- **WHEN** the user saves two profiles and restarts the app
- **THEN** both profiles and their non-secret settings remain available for selection

#### Scenario: No provider configured
- **WHEN** no provider profile or API key exists
- **THEN** recording, import, local transcription, and offline draft generation remain available

### Requirement: Protected credentials
On Windows, API keys MUST be stored in the operating system's credential store and MUST NOT appear in plain settings files, meeting files, application logs, error messages, or exported content. Removing a profile SHALL remove its stored credential.

#### Scenario: Save an API key
- **WHEN** the user saves a profile with an API key
- **THEN** the profile persists without a plaintext key and the credential is available only through protected retrieval for authorized requests

#### Scenario: Delete a profile
- **WHEN** the user removes a provider profile
- **THEN** its saved credential is removed without changing meeting files or other profiles

### Requirement: Safe endpoint policy
Provider requests SHALL use HTTPS with normal certificate verification by default. Plain HTTP SHALL be accepted only for an explicit loopback localhost endpoint, and the app MUST NOT disable TLS verification automatically. Invalid or unsupported URLs SHALL be rejected before any meeting content is sent.

#### Scenario: Remote HTTP URL
- **WHEN** the user tries to use a remote HTTP Base URL
- **THEN** the app rejects the profile or send with a clear explanation and makes no request containing meeting content

#### Scenario: Local loopback provider
- **WHEN** the user explicitly configures an HTTP endpoint on localhost or a loopback address
- **THEN** the app permits that endpoint under the same per-meeting disclosure rules as other providers

### Requirement: Provider generation options
The user SHALL be able to choose a prompt/template and a token limit for a cloud minutes request. The current choices SHALL be shown with the outgoing-content preview before confirmation.

#### Scenario: Customize generation
- **WHEN** the user changes the prompt or token limit before requesting minutes
- **THEN** the preview reflects the selected values and no prior minutes version changes
