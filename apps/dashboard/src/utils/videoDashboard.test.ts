import { describe, it, expect } from 'vitest';
import {
  asUuidOrUndefined,
  createBlankTimelinePoint,
  isHttpUrl,
  mergeMeasuredAndPredictedTimeline,
  normalizeLegacyAssetProxyUrl,
  unwrapHlsProxySourceUrl,
  buildVideoSourceCandidates,
  formatSurveyScore,
  formatSynchrony,
  formatIndexScore,
  formatConfidence,
  formatSynchronyPathway,
  formatNarrativePathway,
  formatTraceSource,
  formatRewardAnticipationPathway,
  normalizeSeekSeconds,
  normalizeIndexToSignedSynchrony,
  isFiniteSynchrony,
  UUID_PATTERN,
  SAMPLE_VIDEO_URL
} from './videoDashboard';
import type { ReadoutTimelinePoint, PredictTracePoint } from '../types';

// ---------------------------------------------------------------------------
// asUuidOrUndefined
// ---------------------------------------------------------------------------

describe('asUuidOrUndefined', () => {
  it('returns valid UUIDs unchanged', () => {
    const uuid = '550e8400-e29b-41d4-a716-446655440000';
    expect(asUuidOrUndefined(uuid)).toBe(uuid);
  });

  it('trims whitespace before testing', () => {
    expect(asUuidOrUndefined('  550e8400-e29b-41d4-a716-446655440000  '))
      .toBe('550e8400-e29b-41d4-a716-446655440000');
  });

  it('returns undefined for null', () => {
    expect(asUuidOrUndefined(null)).toBeUndefined();
  });

  it('returns undefined for undefined', () => {
    expect(asUuidOrUndefined(undefined)).toBeUndefined();
  });

  it('returns undefined for empty string', () => {
    expect(asUuidOrUndefined('')).toBeUndefined();
  });

  it('returns undefined for whitespace-only string', () => {
    expect(asUuidOrUndefined('   ')).toBeUndefined();
  });

  it('returns undefined for non-UUID string', () => {
    expect(asUuidOrUndefined('not-a-uuid')).toBeUndefined();
  });

  it('is case-insensitive', () => {
    expect(asUuidOrUndefined('550E8400-E29B-41D4-A716-446655440000'))
      .toBe('550E8400-E29B-41D4-A716-446655440000');
  });
});

// ---------------------------------------------------------------------------
// createBlankTimelinePoint
// ---------------------------------------------------------------------------

describe('createBlankTimelinePoint', () => {
  it('creates a point with correct tMs and tSec', () => {
    const point = createBlankTimelinePoint(5000);
    expect(point.tMs).toBe(5000);
    expect(point.tSec).toBe(5);
  });

  it('sets all trace fields to null', () => {
    const point = createBlankTimelinePoint(0);
    expect(point.attentionScore).toBeNull();
    expect(point.attentionVelocity).toBeNull();
    expect(point.blinkRate).toBeNull();
    expect(point.blinkInhibition).toBeNull();
    expect(point.rewardProxy).toBeNull();
    expect(point.valenceProxy).toBeNull();
    expect(point.arousalProxy).toBeNull();
    expect(point.noveltyProxy).toBeNull();
    expect(point.trackingConfidence).toBeNull();
  });

  it('initialises auValues as empty object', () => {
    const point = createBlankTimelinePoint(1000);
    expect(point.auValues).toEqual({});
  });

  it('sets IDs to null', () => {
    const point = createBlankTimelinePoint(0);
    expect(point.sceneId).toBeNull();
    expect(point.cutId).toBeNull();
    expect(point.ctaId).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// isHttpUrl
// ---------------------------------------------------------------------------

describe('isHttpUrl', () => {
  it('returns true for http URLs', () => {
    expect(isHttpUrl('http://example.com')).toBe(true);
  });

  it('returns true for https URLs', () => {
    expect(isHttpUrl('https://example.com/path?q=1')).toBe(true);
  });

  it('returns false for ftp URLs', () => {
    expect(isHttpUrl('ftp://example.com')).toBe(false);
  });

  it('returns false for file URIs', () => {
    expect(isHttpUrl('file:///etc/passwd')).toBe(false);
  });

  it('returns false for garbage', () => {
    expect(isHttpUrl('not a url')).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isHttpUrl('')).toBe(false);
  });

  it('returns false for relative paths', () => {
    expect(isHttpUrl('/api/videos')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// mergeMeasuredAndPredictedTimeline
// ---------------------------------------------------------------------------

describe('mergeMeasuredAndPredictedTimeline', () => {
  const makeMeasured = (tMs: number): ReadoutTimelinePoint => ({
    ...createBlankTimelinePoint(tMs),
    attentionScore: 50
  });

  it('returns measured unchanged when predicted is empty', () => {
    const measured = [makeMeasured(0), makeMeasured(1000)];
    const result = mergeMeasuredAndPredictedTimeline(measured, []);
    expect(result).toBe(measured); // same reference
  });

  it('merges prediction into matching measured points', () => {
    const measured = [makeMeasured(0), makeMeasured(1000)];
    const predicted: PredictTracePoint[] = [
      { t_sec: 1, attention: 75, blink_inhibition: 0.9, reward_proxy: 60, dial: 55 }
    ];
    const result = mergeMeasuredAndPredictedTimeline(measured, predicted);
    expect(result).toHaveLength(2);
    expect(result[1].predictedAttentionScore).toBe(75);
    expect(result[1].predictedRewardProxy).toBe(60);
    expect(result[1].predictedBlinkInhibition).toBe(0.9);
    // Original measured field preserved
    expect(result[1].attentionScore).toBe(50);
  });

  it('creates blank points for predictions with no measured counterpart', () => {
    const measured = [makeMeasured(0)];
    const predicted: PredictTracePoint[] = [
      { t_sec: 2, attention: 80, blink_inhibition: 0.5, reward_proxy: null, dial: 50 }
    ];
    const result = mergeMeasuredAndPredictedTimeline(measured, predicted);
    expect(result).toHaveLength(2);
    expect(result[1].tMs).toBe(2000);
    expect(result[1].predictedAttentionScore).toBe(80);
    expect(result[1].attentionScore).toBeNull(); // blank
  });

  it('sorts result by tMs', () => {
    const measured = [makeMeasured(2000)];
    const predicted: PredictTracePoint[] = [
      { t_sec: 0, attention: 10, blink_inhibition: 0.1, reward_proxy: null, dial: 50 },
      { t_sec: 3, attention: 90, blink_inhibition: 0.3, reward_proxy: null, dial: 50 }
    ];
    const result = mergeMeasuredAndPredictedTimeline(measured, predicted);
    expect(result.map((r) => r.tMs)).toEqual([0, 2000, 3000]);
  });

  it('handles null reward_proxy in predictions', () => {
    const measured = [makeMeasured(0)];
    const predicted: PredictTracePoint[] = [
      { t_sec: 0, attention: 42, blink_inhibition: 0.7, reward_proxy: null, dial: 50 }
    ];
    const result = mergeMeasuredAndPredictedTimeline(measured, predicted);
    expect(result[0].predictedRewardProxy).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// unwrapHlsProxySourceUrl
// ---------------------------------------------------------------------------

describe('unwrapHlsProxySourceUrl', () => {
  it('extracts url param from HLS proxy path', () => {
    const input = '/api/video/hls-proxy?url=https%3A%2F%2Fexample.com%2Fvideo.m3u8';
    expect(unwrapHlsProxySourceUrl(input)).toBe('https://example.com/video.m3u8');
  });

  it('returns null for non-proxy paths', () => {
    expect(unwrapHlsProxySourceUrl('/api/videos')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(unwrapHlsProxySourceUrl('')).toBeNull();
  });

  it('returns null for whitespace-only', () => {
    expect(unwrapHlsProxySourceUrl('   ')).toBeNull();
  });

  it('returns null when url param is missing', () => {
    expect(unwrapHlsProxySourceUrl('/api/video/hls-proxy')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// buildVideoSourceCandidates
// ---------------------------------------------------------------------------

describe('buildVideoSourceCandidates', () => {
  it('always includes SAMPLE_VIDEO_URL as fallback', () => {
    const result = buildVideoSourceCandidates(null);
    expect(result).toContain(SAMPLE_VIDEO_URL);
  });

  it('includes source URL as first candidate when valid', () => {
    const result = buildVideoSourceCandidates('https://cdn.example.com/video.mp4');
    expect(result[0]).toBe('https://cdn.example.com/video.mp4');
  });

  it('returns deduplicated list', () => {
    const result = buildVideoSourceCandidates(SAMPLE_VIDEO_URL);
    const unique = new Set(result);
    expect(result.length).toBe(unique.size);
  });

  it('handles undefined input', () => {
    const result = buildVideoSourceCandidates(undefined);
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result).toContain(SAMPLE_VIDEO_URL);
  });
});

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

describe('formatSurveyScore', () => {
  it('formats numbers to 2 decimal places', () => {
    expect(formatSurveyScore(3.14159)).toBe('3.14');
  });
  it('returns n/a for null', () => {
    expect(formatSurveyScore(null)).toBe('n/a');
  });
  it('returns n/a for undefined', () => {
    expect(formatSurveyScore(undefined)).toBe('n/a');
  });
});

describe('formatSynchrony', () => {
  it('formats to 3 decimal places', () => {
    expect(formatSynchrony(0.12345)).toBe('0.123');
  });
  it('returns n/a for null', () => {
    expect(formatSynchrony(null)).toBe('n/a');
  });
});

describe('formatIndexScore', () => {
  it('formats to 1 decimal place', () => {
    expect(formatIndexScore(72.456)).toBe('72.5');
  });
  it('returns n/a for null', () => {
    expect(formatIndexScore(null)).toBe('n/a');
  });
});

describe('formatConfidence', () => {
  it('formats as percentage', () => {
    expect(formatConfidence(0.85)).toBe('85%');
  });
  it('rounds properly', () => {
    expect(formatConfidence(0.999)).toBe('100%');
  });
  it('returns n/a for null', () => {
    expect(formatConfidence(null)).toBe('n/a');
  });
});

describe('formatSynchronyPathway', () => {
  it('maps known values', () => {
    expect(formatSynchronyPathway('direct_panel_gaze')).toBe('Direct panel gaze');
    expect(formatSynchronyPathway('fallback_proxy')).toBe('Fallback proxy');
    expect(formatSynchronyPathway('insufficient_data')).toBe('Insufficient data');
  });
  it('returns Unknown for null', () => {
    expect(formatSynchronyPathway(null)).toBe('Unknown');
  });
  it('returns Unknown for unrecognized values', () => {
    expect(formatSynchronyPathway('something_else')).toBe('Unknown');
  });
});

describe('formatNarrativePathway', () => {
  it('maps timeline_grammar', () => {
    expect(formatNarrativePathway('timeline_grammar')).toBe('Timeline grammar');
  });
  it('returns Unknown for undefined', () => {
    expect(formatNarrativePathway(undefined)).toBe('Unknown');
  });
});

describe('formatTraceSource', () => {
  it('maps all known values', () => {
    expect(formatTraceSource('provided')).toBe('Provided traces');
    expect(formatTraceSource('synthetic_fallback')).toBe('Synthetic fallback');
    expect(formatTraceSource('mixed')).toBe('Mixed sources');
    expect(formatTraceSource('unknown')).toBe('Unknown');
  });
});

describe('formatRewardAnticipationPathway', () => {
  it('maps timeline_dynamics', () => {
    expect(formatRewardAnticipationPathway('timeline_dynamics')).toBe('Timeline dynamics');
  });
});

// ---------------------------------------------------------------------------
// normalizeSeekSeconds
// ---------------------------------------------------------------------------

describe('normalizeSeekSeconds', () => {
  it('clamps negative values to 0', () => {
    expect(normalizeSeekSeconds(-5)).toBe(0);
  });
  it('passes through positive values', () => {
    expect(normalizeSeekSeconds(10)).toBe(10);
  });
  it('returns null for NaN', () => {
    expect(normalizeSeekSeconds(NaN)).toBeNull();
  });
  it('returns null for Infinity', () => {
    expect(normalizeSeekSeconds(Infinity)).toBeNull();
  });
  it('passes through zero', () => {
    expect(normalizeSeekSeconds(0)).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// normalizeIndexToSignedSynchrony
// ---------------------------------------------------------------------------

describe('normalizeIndexToSignedSynchrony', () => {
  it('maps 0 to -1', () => {
    expect(normalizeIndexToSignedSynchrony(0)).toBe(-1);
  });
  it('maps 50 to 0', () => {
    expect(normalizeIndexToSignedSynchrony(50)).toBe(0);
  });
  it('maps 100 to 1', () => {
    expect(normalizeIndexToSignedSynchrony(100)).toBe(1);
  });
  it('clamps values above 100', () => {
    expect(normalizeIndexToSignedSynchrony(200)).toBe(1);
  });
  it('clamps values below 0', () => {
    expect(normalizeIndexToSignedSynchrony(-100)).toBe(-1);
  });
  it('returns null for null', () => {
    expect(normalizeIndexToSignedSynchrony(null)).toBeNull();
  });
  it('returns null for NaN', () => {
    expect(normalizeIndexToSignedSynchrony(NaN)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// isFiniteSynchrony
// ---------------------------------------------------------------------------

describe('isFiniteSynchrony', () => {
  it('returns true for finite numbers', () => {
    expect(isFiniteSynchrony(0.5)).toBe(true);
  });
  it('returns false for null', () => {
    expect(isFiniteSynchrony(null)).toBe(false);
  });
  it('returns false for undefined', () => {
    expect(isFiniteSynchrony(undefined)).toBe(false);
  });
  it('returns false for Infinity', () => {
    expect(isFiniteSynchrony(Infinity)).toBe(false);
  });
  it('returns false for NaN', () => {
    expect(isFiniteSynchrony(NaN)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// UUID_PATTERN
// ---------------------------------------------------------------------------

describe('UUID_PATTERN', () => {
  it('matches valid v4 UUIDs', () => {
    expect(UUID_PATTERN.test('550e8400-e29b-41d4-a716-446655440000')).toBe(true);
  });
  it('rejects short strings', () => {
    expect(UUID_PATTERN.test('550e8400')).toBe(false);
  });
  it('rejects missing dashes', () => {
    expect(UUID_PATTERN.test('550e8400e29b41d4a716446655440000')).toBe(false);
  });
});
