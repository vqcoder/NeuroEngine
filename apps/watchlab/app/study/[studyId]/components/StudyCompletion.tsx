'use client';

import type { AnnotationMarker, TimelineEvent } from '@/lib/schema';
import type { StudyStage } from '@/lib/studyTypes';
import type { VideoLibraryItem } from '@/lib/videoLibrary';

export interface StudyCompletionProps {
  stage: Extract<StudyStage, 'next_video' | 'complete'>;
  nextStudyHref: string | null;
  nextStudyTitle: string | null;
  nextVideoChoice: { item: VideoLibraryItem; href: string } | null;
  annotationMarkers: AnnotationMarker[];
  dialSampleCount: number;
  timeline: TimelineEvent[];
  setStage: (stage: StudyStage) => void;
}

export default function StudyCompletion({
  stage,
  nextStudyHref,
  nextStudyTitle,
  nextVideoChoice,
  annotationMarkers,
  dialSampleCount,
  timeline,
  setStage
}: StudyCompletionProps) {
  return (
    <>
      {stage === 'next_video' && nextVideoChoice ? (
        <section
          data-testid="next-video-panel"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 200,
            background: '#08080a',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            textAlign: 'center'
          }}
        >
          <div style={{ maxWidth: 520, width: '100%' }}>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--accent)',
              marginBottom: 32
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: 'var(--accent)',
                boxShadow: '0 0 8px var(--accent)'
              }} />
              Session recorded
            </div>

            <h1 style={{ fontSize: 32, marginBottom: 12, letterSpacing: '-0.03em' }}>
              Ready for the next one?
            </h1>
            <p style={{ color: 'var(--text-2)', fontSize: 16, marginBottom: 48, lineHeight: 1.5 }}>
              Your responses were saved. Another video is queued up.
            </p>

            <div style={{
              background: 'var(--bg-1)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              marginBottom: 32,
              textAlign: 'left',
              position: 'relative',
              overflow: 'hidden'
            }}>
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                background: 'linear-gradient(90deg, var(--accent), transparent 70%)'
              }} />
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--text-3)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                marginBottom: 8
              }}>
                Up next
              </div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '-0.02em' }}>
                {nextVideoChoice.item.title}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center' }}>
              <a
                href={nextVideoChoice.href}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 10,
                  background: 'var(--accent)',
                  color: '#08080a',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: '0.07em',
                  textTransform: 'uppercase',
                  textDecoration: 'none',
                  padding: '14px 32px',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: '0 0 0 1px rgba(200,240,49,0.4), 0 0 40px rgba(200,240,49,0.15)',
                  width: '100%',
                  justifyContent: 'center'
                }}
                data-testid="watch-next-link"
              >
                Watch next video &rarr;
              </a>
              <button
                onClick={() => setStage('complete')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-3)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  padding: '10px 16px'
                }}
                data-testid="done-for-today-button"
              >
                I&#39;m done for today
              </button>
            </div>
          </div>
        </section>
      ) : null}

      {stage === 'complete' ? (
        <section className="panel stack" data-testid="completion-panel">
          <h2>Session Complete</h2>
          <p>Thank you. Your responses and reaction traces were saved.</p>
          <p className="muted">Timeline events collected: {timeline.length}</p>
          <p className="muted">Annotation markers saved: {annotationMarkers.length}</p>
          <p className="muted">Dial samples collected: {dialSampleCount}</p>
          {nextStudyHref ? (
            <div className="row">
              <a href={nextStudyHref} className="button-link" data-testid="completion-next-study-link">
                Start next study{nextStudyTitle ? `: ${nextStudyTitle}` : ''}
              </a>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
