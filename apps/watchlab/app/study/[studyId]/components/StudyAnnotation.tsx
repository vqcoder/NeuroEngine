'use client';

import type { ReactNode } from 'react';
import type { AnnotationMarker, TimelineEvent } from '@/lib/schema';
import type { MarkerType } from '@/lib/studyTypes';
import { markerLabels } from '@/lib/studyTypes';
import { formatMoment } from '@/lib/studyHelpers';

export interface StudyAnnotationProps {
  /** Pre-rendered <video> element with all event handlers attached. */
  videoElement: ReactNode;
  annotationCursorMs: number;
  annotationDurationMs: number;
  annotationMarkers: AnnotationMarker[];
  annotationNoteDraft: string;
  markerCounts: Record<MarkerType, number>;
  dialModeEnabled: boolean;
  dialValue: number;
  dialSampleCount: number;
  dialEnabled: boolean;
  firstPassEnded: boolean;
  nextStudyHref: string | null;
  nextStudyTitle: string | null;
  videoError: string | null;
  setAnnotationNoteDraft: (value: string) => void;
  seekAnnotationTimeline: (videoTimeMs: number) => void;
  addMarker: (markerType: MarkerType) => void;
  removeMarker: (markerId: string) => void;
  onSkipAnnotation: () => void;
  onContinueToSurvey: () => void;
  setDialModeEnabled: (value: boolean) => void;
  setDialValue: (value: number) => void;
  appendEvent: (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward?: boolean,
    explicitVideoTimeMs?: number,
  ) => void;
}

export default function StudyAnnotation({
  videoElement,
  annotationCursorMs,
  annotationDurationMs,
  annotationMarkers,
  annotationNoteDraft,
  markerCounts,
  dialModeEnabled,
  dialValue,
  dialSampleCount,
  dialEnabled,
  firstPassEnded,
  nextStudyHref,
  nextStudyTitle,
  videoError,
  setAnnotationNoteDraft,
  seekAnnotationTimeline,
  addMarker,
  removeMarker,
  onSkipAnnotation,
  onContinueToSurvey,
  setDialModeEnabled,
  setDialValue,
  appendEvent
}: StudyAnnotationProps) {
  return (
    <section className="panel stack" data-testid="annotation-stage">
      <h2>Post-View Timeline Annotation</h2>
      <p className="muted">
        Scrub the timeline and add timestamped markers. You can add multiple markers per type.
      </p>

      {firstPassEnded && nextStudyHref ? (
        <div className="panel stack next-study-panel" data-testid="next-study-panel">
          <strong>Video ended. Next study is ready.</strong>
          <p className="muted">
            One click launches the next study{nextStudyTitle ? `: ${nextStudyTitle}` : ''}.
          </p>
          <div className="row">
            <a href={nextStudyHref} className="button-link" data-testid="start-next-study-link">
              Start next study
            </a>
          </div>
        </div>
      ) : null}

      {videoElement}

      <div className="panel stack">
        <label htmlFor="annotation-scrubber">
          Timeline scrubber: <strong data-testid="annotation-cursor-ms">{annotationCursorMs}</strong> ms
        </label>
        <input
          id="annotation-scrubber"
          type="range"
          min={0}
          max={Math.max(annotationDurationMs, 1)}
          step={100}
          value={Math.min(annotationCursorMs, Math.max(annotationDurationMs, 1))}
          onChange={(event) => seekAnnotationTimeline(Number(event.target.value))}
          data-testid="annotation-scrubber"
        />
        <small className="muted">
          Current: {formatMoment(annotationCursorMs)} | Duration:{' '}
          {annotationDurationMs > 0 ? formatMoment(annotationDurationMs) : 'Loading...'}
        </small>
      </div>

      <div className="panel stack">
        <label htmlFor="annotation-note">Optional note for next marker</label>
        <textarea
          id="annotation-note"
          rows={2}
          value={annotationNoteDraft}
          onChange={(event) => setAnnotationNoteDraft(event.target.value)}
          placeholder="Add context (optional)"
          data-testid="annotation-note-input"
        />

        <div className="row">
          <button
            onClick={() => addMarker('engaging_moment')}
            className="marker-engaging_moment"
            data-testid="add-marker-engaging"
          >
            + Engaging
          </button>
          <button
            onClick={() => addMarker('confusing_moment')}
            className="marker-confusing_moment"
            data-testid="add-marker-confusing"
          >
            + Confusing
          </button>
          <button
            onClick={() => addMarker('stop_watching_moment')}
            className="marker-stop_watching_moment"
            data-testid="add-marker-stop"
          >
            + Stop watching
          </button>
          <button
            onClick={() => addMarker('cta_landed_moment')}
            className="marker-cta_landed_moment"
            data-testid="add-marker-cta"
          >
            + CTA landed
          </button>
        </div>

        <div className="row">
          <small>Engaging: {markerCounts.engaging_moment}</small>
          <small>Confusing: {markerCounts.confusing_moment}</small>
          <small>Stop-watching: {markerCounts.stop_watching_moment}</small>
          <small>CTA-landed: {markerCounts.cta_landed_moment}</small>
        </div>
      </div>

      <div className="panel stack" data-testid="annotation-marker-list">
        <h3>Markers ({annotationMarkers.length})</h3>
        {annotationMarkers.length === 0 ? (
          <small className="muted">No markers yet.</small>
        ) : (
          annotationMarkers
            .slice()
            .sort((a, b) => a.videoTimeMs - b.videoTimeMs)
            .map((marker) => (
              <div
                key={marker.id}
                className={`scene-marker-chip marker-${marker.markerType}`}
                data-testid="annotation-marker-row"
              >
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span>{markerLabels[marker.markerType]}</span>
                  <small>{formatMoment(marker.videoTimeMs)}</small>
                </div>
                {marker.note ? (
                  <small style={{ fontFamily: 'var(--font-body)', letterSpacing: 0, color: 'var(--text-2)' }}>
                    {marker.note}
                  </small>
                ) : null}
                <div className="row" style={{ gap: 6, marginTop: 2 }}>
                  <button onClick={() => seekAnnotationTimeline(marker.videoTimeMs)}>Seek</button>
                  <button onClick={() => removeMarker(marker.id)}>Remove</button>
                </div>
              </div>
            ))
        )}
      </div>

      {dialEnabled ? (
        <div className="panel stack" data-testid="continuous-dial-panel">
          <h3>Optional Dial Replay</h3>
          <p className="muted">
            Enable only for calibration replay. Dial is not shown during first-pass viewing.
          </p>
          <div className="row">
            <button
              onClick={() => {
                const nextValue = !dialModeEnabled;
                setDialModeEnabled(nextValue);
                appendEvent('annotation_tag_set', {
                  markerType: 'dial_mode_toggle',
                  enabled: nextValue
                });
              }}
              data-testid="toggle-dial-mode"
            >
              {dialModeEnabled ? 'Disable Dial Replay' : 'Enable Dial Replay'}
            </button>
            <small>Samples captured: {dialSampleCount}</small>
          </div>
          <label htmlFor="dial-slider">
            Dial value: <strong data-testid="dial-value">{dialValue}</strong>
          </label>
          <input
            id="dial-slider"
            type="range"
            min={0}
            max={100}
            step={1}
            value={dialValue}
            disabled={!dialModeEnabled}
            onChange={(event) => {
              setDialValue(Number(event.target.value));
            }}
            data-testid="dial-slider"
          />
        </div>
      ) : null}

      <div className="row">
        <button
          onClick={onSkipAnnotation}
          data-testid="annotation-skip-button"
        >
          Skip annotation
        </button>
        <button
          className="primary"
          onClick={onContinueToSurvey}
          data-testid="annotation-continue-button"
        >
          Continue to survey
        </button>
      </div>

      {videoError ? <p className="status-bad">{videoError}</p> : null}
    </section>
  );
}
