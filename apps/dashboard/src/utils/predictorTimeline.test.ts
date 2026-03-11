import { describe, it, expect } from 'vitest';
import {
  clamp,
  toSeekableSecond,
  formatSeconds,
  isLikelyDirectVideoUrl,
  buildPlaybackCandidates,
  deriveTimeline,
  derivePredictorTracks,
  derivePredictorKeyMoments,
  deriveTimelineEvents
} from './predictorTimeline';
import type { PredictTracePoint } from '../types';
import type { PredictorTimelinePoint } from './predictorTimeline';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTracePoint(overrides: Partial<PredictTracePoint> = {}): PredictTracePoint {
  return {
    t_sec: 0,
    reward_proxy: null,
    attention: null,
    blink_inhibition: 50,
    dial: 50,
    ...overrides
  };
}

function makeTimelinePoint(overrides: Partial<PredictorTimelinePoint> = {}): PredictorTimelinePoint {
  return {
    tSec: 0,
    attentionScore: 50,
    rewardProxy: 50,
    attentionVelocity: 0,
    blinkInhibition: 50,
    blinkRate: 0.3,
    dial: 50,
    valenceProxy: 50,
    arousalProxy: 30,
    noveltyProxy: 15,
    trackingConfidence: 1,
    ...overrides
  };
}

// ---------------------------------------------------------------------------
// clamp
// ---------------------------------------------------------------------------

describe('clamp', () => {
  it('returns value when within range', () => {
    expect(clamp(5, 0, 10)).toBe(5);
  });

  it('clamps to min when value is below', () => {
    expect(clamp(-5, 0, 10)).toBe(0);
  });

  it('clamps to max when value is above', () => {
    expect(clamp(15, 0, 10)).toBe(10);
  });

  it('handles equal min and max', () => {
    expect(clamp(5, 3, 3)).toBe(3);
  });

  it('handles negative ranges', () => {
    expect(clamp(0, -10, -5)).toBe(-5);
  });
});

// ---------------------------------------------------------------------------
// toSeekableSecond
// ---------------------------------------------------------------------------

describe('toSeekableSecond', () => {
  it('rounds to 3 decimal places', () => {
    expect(toSeekableSecond(1.23456)).toBe(1.235);
  });

  it('returns 0 for NaN', () => {
    expect(toSeekableSecond(NaN)).toBe(0);
  });

  it('returns 0 for Infinity', () => {
    expect(toSeekableSecond(Infinity)).toBe(0);
  });

  it('returns 0 for negative Infinity', () => {
    expect(toSeekableSecond(-Infinity)).toBe(0);
  });

  it('clamps negative values to 0', () => {
    expect(toSeekableSecond(-5)).toBe(0);
  });

  it('passes through zero', () => {
    expect(toSeekableSecond(0)).toBe(0);
  });

  it('passes through positive values', () => {
    expect(toSeekableSecond(10)).toBe(10);
  });
});

// ---------------------------------------------------------------------------
// formatSeconds
// ---------------------------------------------------------------------------

describe('formatSeconds', () => {
  it('formats zero', () => {
    expect(formatSeconds(0)).toBe('0.0s');
  });

  it('formats whole seconds', () => {
    expect(formatSeconds(5)).toBe('5.0s');
  });

  it('formats fractional seconds with 1 decimal', () => {
    expect(formatSeconds(3.456)).toBe('3.5s');
  });

  it('handles NaN by returning 0.0s', () => {
    expect(formatSeconds(NaN)).toBe('0.0s');
  });

  it('clamps negatives to 0.0s', () => {
    expect(formatSeconds(-1)).toBe('0.0s');
  });
});

// ---------------------------------------------------------------------------
// isLikelyDirectVideoUrl
// ---------------------------------------------------------------------------

describe('isLikelyDirectVideoUrl', () => {
  it('returns false for empty string', () => {
    expect(isLikelyDirectVideoUrl('')).toBe(false);
  });

  it('returns false for whitespace-only string', () => {
    expect(isLikelyDirectVideoUrl('   ')).toBe(false);
  });

  it('detects .mp4 absolute URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/video.mp4')).toBe(true);
  });

  it('detects .webm absolute URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/video.webm')).toBe(true);
  });

  it('detects .m3u8 HLS manifest URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/stream.m3u8')).toBe(true);
  });

  it('detects .mpd DASH URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/manifest.mpd')).toBe(true);
  });

  it('detects .mov URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/clip.mov')).toBe(true);
  });

  it('detects .m4v URLs', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/clip.m4v')).toBe(true);
  });

  it('detects video URLs with query params', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/video.mp4?token=abc')).toBe(true);
  });

  it('detects video URLs with hash fragments', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/video.mp4#t=10')).toBe(true);
  });

  it('detects relative paths with video extensions', () => {
    expect(isLikelyDirectVideoUrl('/assets/video.mp4')).toBe(true);
  });

  it('returns false for non-video URLs', () => {
    expect(isLikelyDirectVideoUrl('https://example.com/page.html')).toBe(false);
  });

  it('detects googlevideo.com videoplayback URLs', () => {
    expect(
      isLikelyDirectVideoUrl('https://rr4---sn-abc.googlevideo.com/videoplayback?itag=137')
    ).toBe(true);
  });

  it('detects URLs with video/ mime parameter', () => {
    expect(
      isLikelyDirectVideoUrl('https://proxy.example.com/stream?mime=video/mp4')
    ).toBe(true);
  });

  it('returns false for invalid URL strings', () => {
    expect(isLikelyDirectVideoUrl('not-a-url')).toBe(false);
  });

  it('case insensitive for extensions', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/VIDEO.MP4')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// buildPlaybackCandidates
// ---------------------------------------------------------------------------

describe('buildPlaybackCandidates', () => {
  it('returns empty array for empty inputs', () => {
    expect(buildPlaybackCandidates()).toEqual([]);
  });

  it('skips empty strings', () => {
    expect(buildPlaybackCandidates('', '  ')).toEqual([]);
  });

  it('deduplicates identical URLs', () => {
    const url = 'https://cdn.example.com/video.mp4';
    const result = buildPlaybackCandidates(url, url);
    const unique = new Set(result);
    expect(result.length).toBe(unique.size);
  });

  it('includes direct video URLs', () => {
    const result = buildPlaybackCandidates('https://cdn.example.com/video.mp4');
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result).toContain('https://cdn.example.com/video.mp4');
  });

  it('filters out non-video URLs', () => {
    const result = buildPlaybackCandidates('https://example.com/page.html');
    expect(result.every((u) => isLikelyDirectVideoUrl(u))).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// deriveTimeline
// ---------------------------------------------------------------------------

describe('deriveTimeline', () => {
  it('returns empty array for empty input', () => {
    expect(deriveTimeline([])).toEqual([]);
  });

  it('sorts output by tSec ascending', () => {
    const points: PredictTracePoint[] = [
      makeTracePoint({ t_sec: 5 }),
      makeTracePoint({ t_sec: 1 }),
      makeTracePoint({ t_sec: 3 })
    ];
    const result = deriveTimeline(points);
    expect(result.map((r) => r.tSec)).toEqual([1, 3, 5]);
  });

  it('uses provided attention when available', () => {
    const points = [makeTracePoint({ t_sec: 0, attention: 72 })];
    const result = deriveTimeline(points);
    expect(result[0].attentionScore).toBe(72);
  });

  it('derives attention from blink_inhibition when attention is null', () => {
    const points = [makeTracePoint({ t_sec: 0, attention: null, blink_inhibition: 50 })];
    const result = deriveTimeline(points);
    // Formula: clamp(30 + (50/100) * 55, 0, 100) = clamp(57.5, 0, 100) = 57.5
    expect(result[0].attentionScore).toBe(57.5);
  });

  it('uses provided reward_proxy when available', () => {
    const points = [makeTracePoint({ t_sec: 0, attention: 50, reward_proxy: 80 })];
    const result = deriveTimeline(points);
    expect(result[0].rewardProxy).toBe(80);
  });

  it('derives reward_proxy when null', () => {
    const points = [makeTracePoint({ t_sec: 0, attention: 60, reward_proxy: null, blink_inhibition: 50, dial: 40 })];
    const result = deriveTimeline(points);
    // Formula: clamp(60*0.55 + (1-0.5)*30 + 40*0.15, 0, 100) = clamp(33 + 15 + 6, 0, 100) = 54
    expect(result[0].rewardProxy).toBe(54);
  });

  it('computes attention velocity between points', () => {
    const points = [
      makeTracePoint({ t_sec: 0, attention: 40 }),
      makeTracePoint({ t_sec: 1, attention: 80 })
    ];
    const result = deriveTimeline(points);
    // First point: velocity = 0 (no previous)
    expect(result[0].attentionVelocity).toBe(0);
    // Second point: velocity = (80 - 40) / 1 = 40
    expect(result[1].attentionVelocity).toBe(40);
  });

  it('uses provided attention_velocity when available', () => {
    const points = [
      makeTracePoint({ t_sec: 0, attention: 50 }),
      makeTracePoint({ t_sec: 1, attention: 50, attention_velocity: 12.3456 })
    ];
    const result = deriveTimeline(points);
    expect(result[1].attentionVelocity).toBe(12.3456);
  });

  it('clamps blink_rate to [0.02, 0.85]', () => {
    const low = [makeTracePoint({ t_sec: 0, blink_rate: 0.001 })];
    const high = [makeTracePoint({ t_sec: 0, blink_rate: 0.99 })];
    expect(deriveTimeline(low)[0].blinkRate).toBe(0.02);
    expect(deriveTimeline(high)[0].blinkRate).toBe(0.85);
  });

  it('derives blink_rate from blink_inhibition when null', () => {
    const points = [makeTracePoint({ t_sec: 0, blink_rate: null, blink_inhibition: 100 })];
    const result = deriveTimeline(points);
    // Formula: clamp(0.45 - 0.35 * (100/100), 0.02, 0.85) = clamp(0.1, 0.02, 0.85) = 0.1
    expect(result[0].blinkRate).toBe(0.1);
  });

  it('clamps valence_proxy to [0, 100]', () => {
    const points = [makeTracePoint({ t_sec: 0, valence_proxy: 150 })];
    expect(deriveTimeline(points)[0].valenceProxy).toBe(100);
  });

  it('clamps arousal_proxy to [0, 100]', () => {
    const points = [makeTracePoint({ t_sec: 0, arousal_proxy: -10 })];
    expect(deriveTimeline(points)[0].arousalProxy).toBe(0);
  });

  it('clamps novelty_proxy to [0, 100]', () => {
    const points = [makeTracePoint({ t_sec: 0, novelty_proxy: 200 })];
    expect(deriveTimeline(points)[0].noveltyProxy).toBe(100);
  });

  it('defaults tracking_confidence to 1 when undefined', () => {
    const points = [makeTracePoint({ t_sec: 0, tracking_confidence: undefined })];
    expect(deriveTimeline(points)[0].trackingConfidence).toBe(1);
  });

  it('clamps tracking_confidence to [0, 1]', () => {
    const points = [makeTracePoint({ t_sec: 0, tracking_confidence: 2 })];
    expect(deriveTimeline(points)[0].trackingConfidence).toBe(1);
  });

  it('rounds output values to at most 4 decimal places', () => {
    const points = [
      makeTracePoint({ t_sec: 1.111111, attention: 33.333333, blink_inhibition: 44.444444, dial: 55.555555 })
    ];
    const result = deriveTimeline(points);
    const str = result[0].attentionScore.toString();
    const decimals = str.includes('.') ? str.split('.')[1].length : 0;
    expect(decimals).toBeLessThanOrEqual(4);
  });
});

// ---------------------------------------------------------------------------
// derivePredictorTracks
// ---------------------------------------------------------------------------

describe('derivePredictorTracks', () => {
  it('returns 8 tracks in TRACK_ORDER', () => {
    const tracks = derivePredictorTracks([], 10);
    expect(tracks).toHaveLength(8);
    expect(tracks.map((t) => t.key)).toEqual([
      'attention_arrest',
      'attentional_synchrony',
      'narrative_control',
      'blink_transport',
      'reward_anticipation',
      'boundary_encoding',
      'cta_reception',
      'au_friction'
    ]);
  });

  it('returns empty windows for empty timeline', () => {
    const tracks = derivePredictorTracks([], 10);
    tracks.forEach((track) => {
      expect(track.windows).toEqual([]);
    });
  });

  it('each track has required fields', () => {
    const tracks = derivePredictorTracks([], 10);
    tracks.forEach((track) => {
      expect(track).toHaveProperty('key');
      expect(track).toHaveProperty('machineName');
      expect(track).toHaveProperty('label');
      expect(track).toHaveProperty('description');
      expect(track).toHaveProperty('color');
      expect(track).toHaveProperty('windows');
    });
  });

  it('generates attention_arrest windows for high reward points', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 30 }),
      makeTimelinePoint({ tSec: 1, rewardProxy: 70 }),
      makeTimelinePoint({ tSec: 2, rewardProxy: 80 }),
      makeTimelinePoint({ tSec: 3, rewardProxy: 30 })
    ];
    const tracks = derivePredictorTracks(timeline, 4);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    expect(arrestTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('generates attentional_synchrony windows for stable high attention', () => {
    // Need >= 1500ms of stable high attention
    const timeline: PredictorTimelinePoint[] = Array.from({ length: 6 }, (_, i) =>
      makeTimelinePoint({ tSec: i * 0.5, attentionScore: 70, attentionVelocity: 1 })
    );
    const tracks = derivePredictorTracks(timeline, 3);
    const syncTrack = tracks.find((t) => t.key === 'attentional_synchrony')!;
    expect(syncTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('generates narrative_control windows for ascending attention trends', () => {
    // Need attentionVelocity > 3 for >= 2000ms
    const timeline: PredictorTimelinePoint[] = Array.from({ length: 6 }, (_, i) =>
      makeTimelinePoint({ tSec: i * 0.5, attentionVelocity: 5 })
    );
    const tracks = derivePredictorTracks(timeline, 3);
    const narTrack = tracks.find((t) => t.key === 'narrative_control')!;
    expect(narTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('generates blink_transport windows for blink suppression', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, blinkInhibition: -20 }),
      makeTimelinePoint({ tSec: 1, blinkInhibition: -25 })
    ];
    const tracks = derivePredictorTracks(timeline, 2);
    const blinkTrack = tracks.find((t) => t.key === 'blink_transport')!;
    expect(blinkTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('generates boundary_encoding windows for sharp transitions', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, attentionVelocity: 0 }),
      makeTimelinePoint({ tSec: 1, attentionVelocity: 25 }),
      makeTimelinePoint({ tSec: 2, attentionVelocity: 0 })
    ];
    const tracks = derivePredictorTracks(timeline, 3);
    const boundaryTrack = tracks.find((t) => t.key === 'boundary_encoding')!;
    expect(boundaryTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('generates au_friction windows for high arousal / low reward', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, arousalProxy: 75, rewardProxy: 30 }),
      makeTimelinePoint({ tSec: 1, arousalProxy: 80, rewardProxy: 20 })
    ];
    const tracks = derivePredictorTracks(timeline, 2);
    const frictionTrack = tracks.find((t) => t.key === 'au_friction')!;
    expect(frictionTrack.windows.length).toBeGreaterThanOrEqual(1);
  });

  it('cta_reception always returns empty windows (no CTA markers in predictor)', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 90, attentionScore: 90 })
    ];
    const tracks = derivePredictorTracks(timeline, 1);
    const ctaTrack = tracks.find((t) => t.key === 'cta_reception')!;
    expect(ctaTrack.windows).toEqual([]);
  });

  it('window scores are rounded to 3 decimal places', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 70.12345 }),
      makeTimelinePoint({ tSec: 1, rewardProxy: 80.67891 })
    ];
    const tracks = derivePredictorTracks(timeline, 2);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    arrestTrack.windows.forEach((w) => {
      if (w.score != null) {
        const str = w.score.toString();
        const decimals = str.includes('.') ? str.split('.')[1].length : 0;
        expect(decimals).toBeLessThanOrEqual(3);
      }
    });
  });
});

// ---------------------------------------------------------------------------
// derivePredictorKeyMoments
// ---------------------------------------------------------------------------

describe('derivePredictorKeyMoments', () => {
  it('returns only hook_window for empty timeline with positive duration', () => {
    const moments = derivePredictorKeyMoments([], 10);
    expect(moments).toHaveLength(1);
    expect(moments[0].type).toBe('hook_window');
  });

  it('always includes a hook_window for non-empty timeline', () => {
    const timeline = [makeTimelinePoint({ tSec: 0, attentionScore: 50 })];
    const moments = derivePredictorKeyMoments(timeline, 10);
    const hookMoments = moments.filter((m) => m.type === 'hook_window');
    expect(hookMoments).toHaveLength(1);
    expect(hookMoments[0].start_ms).toBe(0);
    expect(hookMoments[0].end_ms).toBeLessThanOrEqual(3000);
  });

  it('hook window end is clamped to duration', () => {
    const timeline = [makeTimelinePoint({ tSec: 0 })];
    const moments = derivePredictorKeyMoments(timeline, 1.5);
    const hook = moments.find((m) => m.type === 'hook_window')!;
    expect(hook.end_ms).toBe(1500);
  });

  it('detects reward ramps (attentionVelocity > 2, rewardProxy < 75, >= 1500ms)', () => {
    // 4 points at 0.5s intervals with ascending velocity and low reward = 2000ms total
    const timeline: PredictorTimelinePoint[] = Array.from({ length: 5 }, (_, i) =>
      makeTimelinePoint({
        tSec: i * 0.5,
        attentionVelocity: 3,
        rewardProxy: 50
      })
    );
    // Last point breaks the ramp
    timeline.push(makeTimelinePoint({ tSec: 2.5, attentionVelocity: 0, rewardProxy: 80 }));
    const moments = derivePredictorKeyMoments(timeline, 3);
    const ramps = moments.filter((m) => m.type === 'reward_ramp');
    expect(ramps.length).toBeGreaterThanOrEqual(1);
  });

  it('does not detect reward ramps shorter than 1500ms', () => {
    // 2 points = 500ms of ramp behavior, not enough
    const timeline = [
      makeTimelinePoint({ tSec: 0, attentionVelocity: 3, rewardProxy: 50 }),
      makeTimelinePoint({ tSec: 0.5, attentionVelocity: 3, rewardProxy: 50 }),
      makeTimelinePoint({ tSec: 1, attentionVelocity: 0, rewardProxy: 80 })
    ];
    const moments = derivePredictorKeyMoments(timeline, 1.5);
    const ramps = moments.filter((m) => m.type === 'reward_ramp');
    expect(ramps).toHaveLength(0);
  });

  it('detects dead zones (attentionScore < 35, rewardProxy < 35, >= 2000ms)', () => {
    const timeline: PredictorTimelinePoint[] = Array.from({ length: 6 }, (_, i) =>
      makeTimelinePoint({
        tSec: i * 0.5,
        attentionScore: 20,
        rewardProxy: 20
      })
    );
    // End with recovery
    timeline.push(makeTimelinePoint({ tSec: 3, attentionScore: 70, rewardProxy: 70 }));
    const moments = derivePredictorKeyMoments(timeline, 3.5);
    const deadZones = moments.filter((m) => m.type === 'dead_zone');
    expect(deadZones.length).toBeGreaterThanOrEqual(1);
  });

  it('does not detect dead zones shorter than 2000ms', () => {
    const timeline = [
      makeTimelinePoint({ tSec: 0, attentionScore: 20, rewardProxy: 20 }),
      makeTimelinePoint({ tSec: 0.5, attentionScore: 20, rewardProxy: 20 }),
      makeTimelinePoint({ tSec: 1, attentionScore: 70, rewardProxy: 70 })
    ];
    const moments = derivePredictorKeyMoments(timeline, 1.5);
    const deadZones = moments.filter((m) => m.type === 'dead_zone');
    expect(deadZones).toHaveLength(0);
  });

  it('clamps moment bounds to [0, durationMs]', () => {
    const timeline = [makeTimelinePoint({ tSec: 0 })];
    const moments = derivePredictorKeyMoments(timeline, 5);
    moments.forEach((m) => {
      expect(m.start_ms).toBeGreaterThanOrEqual(0);
      expect(m.end_ms).toBeLessThanOrEqual(5000);
    });
  });

  it('deduplicates identical moments', () => {
    // Same timeline applied twice should still give unique moments
    const timeline = [
      makeTimelinePoint({ tSec: 0, attentionScore: 50 })
    ];
    const moments = derivePredictorKeyMoments(timeline, 5);
    const keys = moments.map((m) => `${m.type}:${m.start_ms}:${m.end_ms}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('sorts moments by start_ms then end_ms', () => {
    const timeline: PredictorTimelinePoint[] = Array.from({ length: 10 }, (_, i) =>
      makeTimelinePoint({
        tSec: i,
        attentionScore: i < 5 ? 20 : 70,
        rewardProxy: i < 5 ? 20 : 70,
        attentionVelocity: 0
      })
    );
    const moments = derivePredictorKeyMoments(timeline, 10);
    for (let i = 1; i < moments.length; i++) {
      const prev = moments[i - 1];
      const curr = moments[i];
      expect(
        prev.start_ms < curr.start_ms ||
        (prev.start_ms === curr.start_ms && prev.end_ms <= curr.end_ms)
      ).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// deriveTimelineEvents
// ---------------------------------------------------------------------------

describe('deriveTimelineEvents', () => {
  it('returns empty array for empty timeline', () => {
    expect(deriveTimelineEvents([])).toEqual([]);
  });

  it('returns top 3 reward moments sorted by tSec', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 90 }),
      makeTimelinePoint({ tSec: 1, rewardProxy: 50 }),
      makeTimelinePoint({ tSec: 2, rewardProxy: 80 }),
      makeTimelinePoint({ tSec: 3, rewardProxy: 70 })
    ];
    const events = deriveTimelineEvents(timeline);
    const rewardEvents = events.filter((e) => e.id.startsWith('reward-'));
    expect(rewardEvents.length).toBeLessThanOrEqual(3);
  });

  it('includes steepest attention drop event', () => {
    // Use distinct tSec values so the drop event doesn't collide with a reward peak
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, attentionVelocity: 0, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 1, attentionVelocity: -15, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 2, attentionVelocity: -5, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 3, attentionVelocity: 0, rewardProxy: 90 }),
      makeTimelinePoint({ tSec: 4, attentionVelocity: 0, rewardProxy: 80 }),
      makeTimelinePoint({ tSec: 5, attentionVelocity: 0, rewardProxy: 70 })
    ];
    const events = deriveTimelineEvents(timeline);
    const dropEvent = events.find((e) => e.title === 'Steepest attention drop');
    expect(dropEvent).toBeDefined();
    expect(dropEvent!.tSec).toBe(1);
  });

  it('includes strongest attention rebound event', () => {
    // Use distinct tSec values so the rebound event doesn't collide with a reward peak
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, attentionVelocity: 0, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 1, attentionVelocity: 20, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 2, attentionVelocity: 5, rewardProxy: 10 }),
      makeTimelinePoint({ tSec: 3, attentionVelocity: 0, rewardProxy: 90 }),
      makeTimelinePoint({ tSec: 4, attentionVelocity: 0, rewardProxy: 80 }),
      makeTimelinePoint({ tSec: 5, attentionVelocity: 0, rewardProxy: 70 })
    ];
    const events = deriveTimelineEvents(timeline);
    const reboundEvent = events.find((e) => e.title === 'Strongest attention rebound');
    expect(reboundEvent).toBeDefined();
    expect(reboundEvent!.tSec).toBe(1);
  });

  it('deduplicates events at the same seekable second', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 1.0001, rewardProxy: 95, attentionVelocity: -20 }),
      makeTimelinePoint({ tSec: 1.0002, rewardProxy: 90, attentionVelocity: 20 })
    ];
    const events = deriveTimelineEvents(timeline);
    const tSecValues = events.map((e) => e.tSec);
    // At the same seekable second, first event wins
    const uniqueTs = new Set(tSecValues);
    expect(tSecValues.length).toBe(uniqueTs.size);
  });

  it('events are sorted by tSec ascending', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 3, rewardProxy: 90, attentionVelocity: -10 }),
      makeTimelinePoint({ tSec: 1, rewardProxy: 80, attentionVelocity: 15 }),
      makeTimelinePoint({ tSec: 5, rewardProxy: 70, attentionVelocity: 0 })
    ];
    const events = deriveTimelineEvents(timeline);
    for (let i = 1; i < events.length; i++) {
      expect(events[i].tSec).toBeGreaterThanOrEqual(events[i - 1].tSec);
    }
  });

  it('peak reward event title is "Peak reward moment"', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 95, attentionVelocity: 0 }),
      makeTimelinePoint({ tSec: 1, rewardProxy: 50, attentionVelocity: 0 })
    ];
    const events = deriveTimelineEvents(timeline);
    const peak = events.find((e) => e.title === 'Peak reward moment');
    expect(peak).toBeDefined();
  });

  it('event secondary field includes numeric detail', () => {
    const timeline: PredictorTimelinePoint[] = [
      makeTimelinePoint({ tSec: 0, rewardProxy: 85, attentionVelocity: 0 })
    ];
    const events = deriveTimelineEvents(timeline);
    const rewardEvent = events.find((e) => e.id.startsWith('reward-'));
    expect(rewardEvent?.secondary).toContain('reward_proxy');
  });
});
