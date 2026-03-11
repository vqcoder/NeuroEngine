// ---------------------------------------------------------------------------
// buildSurveyAnalyticsHighlights — extracted from study-client.tsx (A21)
// ---------------------------------------------------------------------------

import type { AnnotationMarker, QualitySample, TimelineEvent } from '@/lib/schema';
import type { SurveyAnalyticsHighlight } from '@/lib/studyTypes';

export const buildSurveyAnalyticsHighlights = (
  timeline: TimelineEvent[],
  markers: AnnotationMarker[],
  qualitySamples: QualitySample[]
): SurveyAnalyticsHighlight[] => {
  const byBucket = new Map<string, SurveyAnalyticsHighlight>();

  const push = (candidate: Omit<SurveyAnalyticsHighlight, 'id'>) => {
    const bucket = Math.round(candidate.videoTimeMs / 1000);
    const key = `${candidate.category}:${bucket}`;
    const existing = byBucket.get(key);
    if (!existing || candidate.signalScore > existing.signalScore) {
      byBucket.set(key, {
        ...candidate,
        id: `${candidate.category}-${bucket}`
      });
    }
  };

  for (const marker of markers) {
    if (marker.markerType === 'engaging_moment') {
      push({
        videoTimeMs: marker.videoTimeMs,
        category: 'engagement',
        title: 'Viewer tagged high engagement',
        detail: marker.note ?? 'Engaging moment was explicitly tagged.',
        signalScore: 0.9
      });
    } else if (marker.markerType === 'confusing_moment') {
      push({
        videoTimeMs: marker.videoTimeMs,
        category: 'confusion',
        title: 'Viewer tagged confusion/friction',
        detail: marker.note ?? 'Confusing moment was explicitly tagged.',
        signalScore: 0.88
      });
    } else if (marker.markerType === 'stop_watching_moment') {
      push({
        videoTimeMs: marker.videoTimeMs,
        category: 'drop',
        title: 'Potential abandonment moment',
        detail: marker.note ?? 'Viewer flagged a stop-watching impulse.',
        signalScore: 0.92
      });
    } else if (marker.markerType === 'cta_landed_moment') {
      push({
        videoTimeMs: marker.videoTimeMs,
        category: 'cta',
        title: 'CTA/key message landed',
        detail: marker.note ?? 'Viewer marked CTA/message impact.',
        signalScore: 0.86
      });
    }
  }

  const playbackEvents = timeline.filter((event) =>
    ['rewind', 'pause', 'seek', 'window_blur', 'visibility_hidden'].includes(event.type)
  );
  for (const event of playbackEvents) {
    const detail = event.details ? JSON.stringify(event.details) : '';
    if (event.type === 'rewind') {
      push({
        videoTimeMs: event.videoTimeMs,
        category: 'confusion',
        title: 'Rewind behavior detected',
        detail:
          detail.length > 0
            ? `Replay behavior around this point: ${detail}`
            : 'User rewound near this point, often a reprocessing signal.',
        signalScore: 0.8
      });
    } else if (event.type === 'pause') {
      push({
        videoTimeMs: event.videoTimeMs,
        category: 'playback',
        title: 'Pause behavior detected',
        detail:
          detail.length > 0
            ? `Pause event context: ${detail}`
            : 'User paused around this point.',
        signalScore: 0.65
      });
    } else if (event.type === 'seek') {
      push({
        videoTimeMs: event.videoTimeMs,
        category: 'playback',
        title: 'Seek behavior detected',
        detail:
          detail.length > 0
            ? `Seek transition context: ${detail}`
            : 'User sought to another part of the timeline here.',
        signalScore: 0.7
      });
    } else if (event.type === 'window_blur' || event.type === 'visibility_hidden') {
      push({
        videoTimeMs: event.videoTimeMs,
        category: 'drop',
        title: 'Attention interruption signal',
        detail: 'Tab/app lost foreground around this timestamp.',
        signalScore: 0.72
      });
    }
  }

  const lowQualitySamples = qualitySamples
    .filter(
      (sample) =>
        sample.trackingConfidence < 0.45 ||
        sample.qualityScore < 0.45 ||
        sample.qualityFlags.includes('face_lost')
    )
    .sort((a, b) => a.trackingConfidence - b.trackingConfidence)
    .slice(0, 6);

  for (const sample of lowQualitySamples) {
    push({
      videoTimeMs: sample.videoTimeMs,
      category: 'quality',
      title: 'Low tracking confidence window',
      detail: `Quality flags: ${
        sample.qualityFlags.length > 0 ? sample.qualityFlags.join(', ') : 'none'
      }`,
      signalScore: 1 - sample.trackingConfidence
    });
  }

  return [...byBucket.values()]
    .sort((a, b) => a.videoTimeMs - b.videoTimeMs || b.signalScore - a.signalScore)
    .slice(0, 18);
};
