'use client';

export interface StudyOnboardingProps {
  title: string;
  studyId: string;
  loadingConfig: boolean;
  participantName: string;
  participantEmail: string;
  setParticipantName: (value: string) => void;
  setParticipantEmail: (value: string) => void;
  onAgree: () => void;
}

export default function StudyOnboarding({
  title,
  studyId,
  loadingConfig,
  participantName,
  participantEmail,
  setParticipantName,
  setParticipantEmail,
  onAgree
}: StudyOnboardingProps) {
  return (
    <main>
      <div className="panel stack onboarding-panel" data-testid="consent-screen">
        <h1>{loadingConfig ? `Study ${studyId}` : title}</h1>
        <p>
          Participation is voluntary. Webcam access is required to capture reaction signals during
          the study.
        </p>
        <p>
          We will process raw webcam frames and derived features (for example AU traces, blink
          dynamics, coarse gaze-on-screen proxy, and quality/confidence metrics). We do not claim
          direct dopamine measurement or precise eye tracking.
        </p>
        <p className="muted">
          If enabled for this study, post-view chat reflections may be processed by a language
          model provider to generate follow-up questions.
        </p>
        <p className="muted">
          Raw media and derived features follow study retention/deletion policy. You can stop at
          any time.
        </p>
        <p className="muted">
          Flow: consent, camera check, passive first viewing, timeline annotation, then survey.
        </p>
        <div className="stack" style={{ gap: 10 }}>
          <div className="stack" style={{ gap: 4 }}>
            <label htmlFor="participant-name">Your name</label>
            <input
              id="participant-name"
              type="text"
              placeholder="First and last name"
              value={participantName}
              onChange={(e) => setParticipantName(e.target.value)}
              style={{
                background: 'var(--bg-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '9px 12px',
                fontSize: 14,
                color: 'var(--text-1)',
                outline: 'none',
                width: '100%',
                fontFamily: 'var(--font-body)'
              }}
              data-testid="participant-name-input"
              autoComplete="name"
            />
          </div>
          <div className="stack" style={{ gap: 4 }}>
            <label htmlFor="participant-email">Email address</label>
            <input
              id="participant-email"
              type="email"
              placeholder="you@example.com"
              value={participantEmail}
              onChange={(e) => setParticipantEmail(e.target.value)}
              style={{
                background: 'var(--bg-2)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '9px 12px',
                fontSize: 14,
                color: 'var(--text-1)',
                outline: 'none',
                width: '100%',
                fontFamily: 'var(--font-body)'
              }}
              data-testid="participant-email-input"
              autoComplete="email"
            />
          </div>
        </div>
        <div className="row">
          <button
            className="primary"
            onClick={onAgree}
            disabled={!participantName.trim() || !participantEmail.trim()}
            data-testid="agree-button"
          >
            I agree and continue
          </button>
        </div>
      </div>
    </main>
  );
}
