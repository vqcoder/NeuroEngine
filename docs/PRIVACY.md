# PRIVACY

## Consent and participation

- Study participation is optional. Participants can decline, stop early, or withdraw.
- Consent is required before any webcam capture starts.
- Webcam collection requirements are study-configurable. If webcam is required for a specific study, this must be stated clearly in consent copy.

## Data classes

- Raw capture:
  - webcam frames and related media timestamps
  - playback telemetry (play/pause/seek/mute/focus/visibility events)
- Derived features:
  - AU traces
  - blink events and blink inhibition metrics
  - face/head-pose/gaze-on-screen proxy signals
  - quality and confidence metrics
- Self-report labels:
  - post-view timeline markers
  - survey responses

## Capability boundaries

- Outputs are proxies and quality-dependent estimates, not direct dopamine or biochemical measurements.
- Gaze is a coarse on-screen proxy from laptop webcam signals, not precise eye tracking or fixation mapping.
- Face signals are diagnostic model inputs and do not provide definitive emotion truth labels on their own.

## Retention and deletion

- Prefer retaining derived features over raw webcam media whenever feasible.
- Restrict raw media access to authorized roles only.
- Apply configured retention windows for raw media and derived outputs.
- Support secure deletion workflows for media artifacts and associated session data per project policy.

## Operational safeguards

- Use pseudonymous participant IDs by default.
- Encrypt data in transit and at rest.
- Audit ingestion and access patterns.
- Redact sensitive fields and credential-like values from logs.
- Run privacy observability checks for biometric pathways (tracking confidence context, low-confidence windows, trace-source fallback flags).
- Disallow protected-trait inference in self-relevance/social matching logic and related copy.
