'use client';

import type { MicStatus } from '../hooks/useAudioReaction';

export interface StudyMicCheckProps {
  onAllow: () => void;
  onSkip: () => void;
  onConfirm: () => void;
  micStatus: MicStatus;
  micEnergyLevel: number;
}

export default function StudyMicCheck({
  onAllow,
  onSkip,
  onConfirm,
  micStatus,
  micEnergyLevel,
}: StudyMicCheckProps) {
  const isRequesting = micStatus === 'requesting';
  const isGranted = micStatus === 'granted';

  return (
    <main className="camera-stage-full">
      <div className="camera-layout">
        <div className="panel stack" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
          <h2>Optional: Microphone Access</h2>

          {!isGranted && (
            <>
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
            </>
          )}

          {isGranted && (
            <>
              <p style={{ color: '#22c55e', fontWeight: 600, marginTop: 8 }}>
                Microphone connected &#10003;
              </p>

              <div
                style={{
                  width: '100%',
                  height: 12,
                  borderRadius: 6,
                  background: '#334155',
                  overflow: 'hidden',
                  marginTop: 12,
                }}
              >
                <div
                  style={{
                    width: `${Math.min(micEnergyLevel * 100, 100)}%`,
                    height: '100%',
                    borderRadius: 6,
                    background: 'linear-gradient(90deg, #22c55e, #4ade80)',
                    transition: 'width 80ms ease-out',
                  }}
                />
              </div>

              <p style={{ marginTop: 12, color: '#94a3b8', fontSize: '0.9rem' }}>
                Say something or clap to test your mic
              </p>

              <button
                className="primary"
                onClick={onConfirm}
                style={{ marginTop: 16 }}
              >
                Looks good, continue &rarr;
              </button>

              <small style={{ display: 'block', marginTop: 8, color: '#64748b' }}>
                Not working? Check your system mic settings or Skip below
              </small>
            </>
          )}

          {micStatus === 'denied' && (
            <p className="status-warn" style={{ marginTop: 12 }}>
              Microphone access was denied. You can still continue without it.
            </p>
          )}

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

          <small style={{ display: 'block', marginTop: 16, color: '#64748b' }}>
            No audio is stored. Only reaction type and timing.
          </small>
        </div>
      </div>
    </main>
  );
}
