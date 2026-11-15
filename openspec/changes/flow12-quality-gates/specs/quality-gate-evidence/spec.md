# Spec Delta

## Purpose

Turn feature completion claims into auditable acceptance decisions without conflating code, automated verification, real-hardware validation and user sign-off.

## ADDED Requirements

### Requirement: Evidence-based status per gate
The project SHALL track each gate as NOT_IMPLEMENTED, IMPLEMENTED_UNVERIFIED, AUTOMATED_VERIFIED, MANUAL_VERIFIED, ACCEPTED or BLOCKED. A reviewer MUST NOT mark ACCEPTED solely because source code exists, implementation tasks are checked or a historical test report states “passed.”

#### Scenario: Implementation tasks are complete but hardware verification is pending
- **WHEN** M1 code tasks and automated recording tests are complete but AT-01, AT-02 or AT-10 has no real-device evidence
- **THEN** G1 remains unaccepted and the missing acceptance cases are named as blockers

#### Scenario: Controlled ASR test has passed
- **WHEN** a representative 30-minute offline ASR run passes with an attributable log but no live dual-source recording is available
- **THEN** G2 can retain independent automated evidence while G1 and whole-journey G5 remain blocked

### Requirement: Requirement-to-evidence traceability
Every gate acceptance SHALL have a traceability record containing requirement and scenario IDs, full commit SHA, target Windows build, application/package hash if applicable, exact command or manual procedure, expected/actual result, raw exit status, evidence reference, date and accountable reviewer.

#### Scenario: Reviewer opens an acceptance record
- **WHEN** a reviewer inspects a claimed passing gate
- **THEN** the reviewer can identify which build and input were tested and reproduce or audit every mandatory case

#### Scenario: Evidence is missing
- **WHEN** a mandatory acceptance case has no attributed result or identifiable reviewer
- **THEN** the gate SHALL NOT become ACCEPTED even if other cases pass

### Requirement: Fresh evidence after changes
A change affecting an accepted requirement SHALL require relevant tests and cross-process regression checks to be rerun against the new commit before the gate is accepted for that commit. Prior evidence MUST remain available as historical evidence, not current approval.

#### Scenario: Recording state machine changes
- **WHEN** a PR changes capture, pause, storage or recovery logic
- **THEN** G1 regression tasks and the relevant real-device evidence are re-evaluated before the new release is accepted

### Requirement: Gate dependencies and scoped claims
The project SHALL keep G0 bridge/build, G1 capture, G2 offline transcription, G3 minutes/privacy, G4 independently managed actions, G5 end-to-end and G6 Windows release separate. G5 that advertises tracked actions MUST require accepted G0–G4. A narrower minutes-only release MAY omit G4 only if user-facing scope clearly identifies action suggestions as part of minutes, not independently managed tasks.

#### Scenario: Minutes include action suggestions but no task entity exists
- **WHEN** G3 passes and the UI shows extracted action suggestions without task status/ownership persistence
- **THEN** the project MAY claim source-linked action suggestions but MUST NOT claim independent action item management or full G5 acceptance

#### Scenario: Release candidate lacks clean Windows evidence
- **WHEN** development-host tests pass but clean Windows 10/11 package checks remain open
- **THEN** G6 stays unaccepted independently of G0–G3 results

### Requirement: Evidence privacy
Acceptance evidence SHALL avoid raw confidential transcripts, recordings, API keys and unredacted outbound payloads. Tests of Restricted mode SHALL record connection attempts and behavior without persisting confidential content into public logs.

#### Scenario: Privacy test is documented
- **WHEN** a tester records a Restricted-mode negative test
- **THEN** the evidence shows zero unauthorized content egress using counters/metadata rather than exposing meeting content
