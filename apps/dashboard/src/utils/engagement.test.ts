import { describe, it, expect } from 'vitest';
import {
  mapSummaryToTimeline,
  computeGoldenScenes,
  computeDeadZones
} from './engagement';
import type { SceneMetric, TimelinePoint, VideoSummary, TraceBucket } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeBucket(overrides: Partial<TraceBucket> = {}): TraceBucket {
  return {
    bucket_start_ms: 0,
    samples: 10,
    mean_brightness: 120,
    face_ok_rate: 0.95,
    landmarks_ok_rate: 0.92,
    blink_rate: 0.3,
    mean_dial: null,
    mean_au_norm: { AU12: 0.4, AU06: 0.2, AU04: 0.1 },
    ...overrides
  };
}

function makeScene(start_ms: number, end_ms: number, label: string): SceneMetric {
  return {
    scene_index: 0,
    label,
    start_ms,
    end_ms,
    samples: 10,
    face_ok_rate: 0.9,
    blink_rate: 0.2,
    mean_au12: 0.3
  };
}

function makeTimelinePoint(overrides: Partial<TimelinePoint> = {}): TimelinePoint {
  return {
    tMs: 0,
    tSec: 0,
    attention: 50,
    dial: null,
    blinkRate: 0.2,
    blinkInhibition: 0.3,
    rewardProxy: null,
    gazeProxy: null,
    qualityScore: null,
    qualityConfidence: null,
    faceOkRate: 0.95,
    sceneId: null,
    cutId: null,
    ctaId: null,
    au12: 0.3,
    au6: 0.2,
    au4: 0.1,
    ...overrides
  };
}

// ---------------------------------------------------------------------------
// mapSummaryToTimeline
// ---------------------------------------------------------------------------

describe('mapSummaryToTimeline', () => {
  it('maps trace_buckets to timeline points', () => {
    const summary: VideoSummary = {
      video_id: 'test',
      trace_buckets: [
        makeBucket({ bucket_start_ms: 0 }),
        makeBucket({ bucket_start_ms: 1000 })
      ],
      scene_metrics: [],
      qc_stats: {
        sessions_count: 1,
        participants_count: 1,
        total_trace_points: 20,
        missing_trace_sessions: 0,
        face_ok_rate: 0.95,
        landmarks_ok_rate: 0.92,
        mean_brightness: 120
      },
      annotations: []
    };

    const result = mapSummaryToTimeline(summary);
    expect(result).toHaveLength(2);
    expect(result[0].tMs).toBe(0);
    expect(result[0].tSec).toBe(0);
    expect(result[1].tMs).toBe(1000);
    expect(result[1].tSec).toBe(1);
  });

  it('prefers passive_traces over trace_buckets when present', () => {
    const summary: VideoSummary = {
      video_id: 'test',
      trace_buckets: [makeBucket({ bucket_start_ms: 0 })],
      passive_traces: [
        makeBucket({ bucket_start_ms: 500 }),
        makeBucket({ bucket_start_ms: 1500 })
      ],
      scene_metrics: [],
      qc_stats: {
        sessions_count: 1,
        participants_count: 1,
        total_trace_points: 20,
        missing_trace_sessions: 0,
        face_ok_rate: 0.95,
        landmarks_ok_rate: 0.92,
        mean_brightness: 120
      },
      annotations: []
    };

    const result = mapSummaryToTimeline(summary);
    expect(result).toHaveLength(2);
    expect(result[0].tMs).toBe(500);
    expect(result[1].tMs).toBe(1500);
  });

  it('returns attention scores scaled 0-100', () => {
    const summary: VideoSummary = {
      video_id: 'test',
      trace_buckets: [
        makeBucket({ bucket_start_ms: 0, mean_au_norm: { AU12: 0, AU06: 0, AU04: 0 }, blink_rate: 0 }),
        makeBucket({ bucket_start_ms: 1000, mean_au_norm: { AU12: 1, AU06: 1, AU04: 0 }, blink_rate: 0 })
      ],
      scene_metrics: [],
      qc_stats: {
        sessions_count: 1, participants_count: 1, total_trace_points: 20,
        missing_trace_sessions: 0, face_ok_rate: 0.95, landmarks_ok_rate: 0.92, mean_brightness: 120
      },
      annotations: []
    };

    const result = mapSummaryToTimeline(summary);
    // First bucket has lower AU values → lower attention
    // Second bucket has higher AU values → higher attention
    expect(result[0].attention).toBeLessThan(result[1].attention);
    // Scaled to 0–100
    result.forEach((point) => {
      expect(point.attention).toBeGreaterThanOrEqual(0);
      expect(point.attention).toBeLessThanOrEqual(100);
    });
  });

  it('rounds output to 4 decimal places', () => {
    const summary: VideoSummary = {
      video_id: 'test',
      trace_buckets: [makeBucket({ bucket_start_ms: 0 })],
      scene_metrics: [],
      qc_stats: {
        sessions_count: 1, participants_count: 1, total_trace_points: 10,
        missing_trace_sessions: 0, face_ok_rate: 0.95, landmarks_ok_rate: 0.92, mean_brightness: 120
      },
      annotations: []
    };

    const result = mapSummaryToTimeline(summary);
    const str = result[0].blinkRate.toString();
    const decimals = str.includes('.') ? str.split('.')[1].length : 0;
    expect(decimals).toBeLessThanOrEqual(4);
  });

  it('handles empty trace_buckets', () => {
    const summary: VideoSummary = {
      video_id: 'test',
      trace_buckets: [],
      scene_metrics: [],
      qc_stats: {
        sessions_count: 0, participants_count: 0, total_trace_points: 0,
        missing_trace_sessions: 0, face_ok_rate: 0, landmarks_ok_rate: 0, mean_brightness: 0
      },
      annotations: []
    };

    const result = mapSummaryToTimeline(summary);
    expect(result).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// computeGoldenScenes
// ---------------------------------------------------------------------------

describe('computeGoldenScenes', () => {
  it('returns empty array for empty points', () => {
    expect(computeGoldenScenes([], [])).toEqual([]);
  });

  it('returns top N peaks sorted by score descending', () => {
    const points: TimelinePoint[] = [
      makeTimelinePoint({ tMs: 0, tSec: 0, attention: 20 }),
      makeTimelinePoint({ tMs: 1000, tSec: 1, attention: 90 }),
      makeTimelinePoint({ tMs: 2000, tSec: 2, attention: 60 }),
      makeTimelinePoint({ tMs: 3000, tSec: 3, attention: 95 }),
      makeTimelinePoint({ tMs: 4000, tSec: 4, attention: 30 })
    ];
    const scenes = [makeScene(0, 5000, 'Scene 1')];

    const result = computeGoldenScenes(points, scenes, 2);
    expect(result).toHaveLength(2);
    // Top scores should come first
    expect(result[0].score).toBeGreaterThanOrEqual(result[1].score);
  });

  it('respects the limit parameter', () => {
    const points = Array.from({ length: 10 }, (_, i) =>
      makeTimelinePoint({ tMs: i * 1000, tSec: i, attention: i * 10 })
    );
    const result = computeGoldenScenes(points, [], 3);
    expect(result).toHaveLength(3);
  });

  it('assigns scene labels from sceneMetrics', () => {
    const points = [
      makeTimelinePoint({ tMs: 500, tSec: 0.5, attention: 80 })
    ];
    const scenes = [makeScene(0, 1000, 'Intro')];

    const result = computeGoldenScenes(points, scenes);
    expect(result[0].sceneLabel).toBe('Intro');
  });

  it('labels as Unlabeled when outside scene ranges', () => {
    const points = [
      makeTimelinePoint({ tMs: 5000, tSec: 5, attention: 80 })
    ];
    const scenes = [makeScene(0, 1000, 'Intro')];

    const result = computeGoldenScenes(points, scenes);
    expect(result[0].sceneLabel).toBe('Unlabeled');
  });
});

// ---------------------------------------------------------------------------
// computeDeadZones
// ---------------------------------------------------------------------------

describe('computeDeadZones', () => {
  it('returns empty array for empty points', () => {
    expect(computeDeadZones([], [])).toEqual([]);
  });

  it('detects low-attention regions', () => {
    // Create a sequence: high, low, low, low, high
    const points: TimelinePoint[] = [
      makeTimelinePoint({ tMs: 0, tSec: 0, attention: 90, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 1000, tSec: 1, attention: 10, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 2000, tSec: 2, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 3000, tSec: 3, attention: 8, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 4000, tSec: 4, attention: 85, blinkRate: 0.1, au4: 0.05 })
    ];

    const result = computeDeadZones(points, []);
    // Should find at least one dead zone in the low-attention middle
    expect(result.length).toBeGreaterThanOrEqual(1);
    expect(result[0].meanAttention).toBeLessThan(50);
  });

  it('respects the limit parameter', () => {
    // Generate many alternating high/low points to create multiple dead zones
    const points: TimelinePoint[] = [];
    for (let i = 0; i < 20; i++) {
      points.push(
        makeTimelinePoint({
          tMs: i * 1000,
          tSec: i,
          attention: i % 4 < 2 ? 5 : 95,
          blinkRate: 0.1,
          au4: 0.05
        })
      );
    }

    const result = computeDeadZones(points, [], 2);
    expect(result.length).toBeLessThanOrEqual(2);
  });

  it('includes scene labels in dead zone results', () => {
    const points = [
      makeTimelinePoint({ tMs: 0, tSec: 0, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 1000, tSec: 1, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 2000, tSec: 2, attention: 95, blinkRate: 0.1, au4: 0.05 })
    ];
    const scenes = [makeScene(0, 3000, 'Opening')];

    const result = computeDeadZones(points, scenes);
    if (result.length > 0) {
      expect(result[0].sceneLabel).toBe('Opening');
    }
  });

  it('sorts dead zones by duration descending', () => {
    // Create two distinct dead zones of different lengths
    const points: TimelinePoint[] = [
      // Short dead zone
      makeTimelinePoint({ tMs: 0, tSec: 0, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 1000, tSec: 1, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      // Recovery
      makeTimelinePoint({ tMs: 2000, tSec: 2, attention: 95, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 3000, tSec: 3, attention: 95, blinkRate: 0.1, au4: 0.05 }),
      // Longer dead zone
      makeTimelinePoint({ tMs: 4000, tSec: 4, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 5000, tSec: 5, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 6000, tSec: 6, attention: 5, blinkRate: 0.1, au4: 0.05 }),
      makeTimelinePoint({ tMs: 7000, tSec: 7, attention: 95, blinkRate: 0.1, au4: 0.05 })
    ];

    const result = computeDeadZones(points, []);
    if (result.length >= 2) {
      expect(result[0].durationSec).toBeGreaterThanOrEqual(result[1].durationSec);
    }
  });
});
