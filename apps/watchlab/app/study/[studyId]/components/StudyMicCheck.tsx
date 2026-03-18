'use client';

import type { MicStatus } from '../hooks/useAudioReaction';

export interface StudyMicCheckProps {
  onAllow: () => void;
  onSkip: () => void;
  micStatus: MicStatus;
}

export default function StudyMicCheck({ onAllow, onSkip, micStatus }: StudyMicCheckProps) {
  const isRequesting = micStatus === 'requesting';

  return (
    <main className="camera-stage-full">
      <div className="camera-layout">
        <div className="panel stack" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
          <h2>Optional: Microphone Access</h2>
          <p>
            Allowing mic access lets us detect your reactions (laughs, gasps) during the video.
            No audio is recorded &mdash; only reaction moments are captured.
          </p>

          <button
            className="primary"
            onClick={onAllow}
            disabled={isRequesting}
            style={{ marginTop: 16 }}
          >
            {isRequesting ? 'Requesting...' : 'Allow Microphone'}
          </button>

          <button
            onClick={onSkip}
            disabled={isRequesting}
            style={{
              marginTop: 8,
              background: 'none',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              textDecoration: 'underline',
              fontSize: '0.9rem',
            }}
          >
            Skip
          </button>

          {micStatus === 'denied' && (
            <p className="status-warn" style={{ marginTop: 12 }}>
              Microphone access was denied. You can still continue without it.
            </p>
          )}

          <small style={{ display: 'block', marginTop: 16, color: '#64748b' }}>
            No audio is stored. Only reaction type and timing.
          </small>
        </div>
      </div>
    </main>
  );
}
