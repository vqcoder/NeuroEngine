import { describe, it, expect } from 'vitest';
import { readoutPayloadSchema, readoutSchemaVersion } from './readoutPayload';

// ---------------------------------------------------------------------------
// Helper: build a minimal valid payload matching the current schema shape.
// Override individual fields by spreading into the returned object.
// ---------------------------------------------------------------------------

function makeValidPayload(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: '1.0.0',
    video_id: '550e8400-e29b-41d4-a716-446655440000',
    aggregate: false,
    duration_ms: 30000,
    timebase: { window_ms: 1000, step_ms: 500 },
    context: {
      scenes: [{ scene_index: 0, start_ms: 0, end_ms: 30000 }],
      cuts: [],
      cta_markers: []
    },
    traces: {
      attention_score: [{ video_time_ms: 0, value: 50 }],
      attention_velocity: [],
      blink_rate: [],
      blink_inhibition: [],
      reward_proxy: [],
      valence_proxy: [],
      arousal_proxy: [],
      novelty_proxy: [],
      tracking_confidence: []
    },
    segments: {
      attention_gain_segments: [],
      attention_loss_segments: [],
      golden_scenes: [],
      dead_zones: [],
      confusion_segments: []
    },
    labels: {
      annotations: []
    },
    quality: {
      session_quality_summary: {
        sessions_count: 5,
        participants_count: 5,
        total_trace_points: 1000,
        face_ok_rate: 0.95,
        mean_brightness: 120,
        low_confidence_windows: 0
      },
      low_confidence_windows: []
    },
    ...overrides
  };
}

// ---------------------------------------------------------------------------
// Schema version
// ---------------------------------------------------------------------------

describe('readoutSchemaVersion', () => {
  it('is a non-empty semver string', () => {
    expect(readoutSchemaVersion).toBe('1.0.0');
  });
});

// ---------------------------------------------------------------------------
// readoutPayloadSchema — validation
// ---------------------------------------------------------------------------

describe('readoutPayloadSchema', () => {
  it('accepts a minimal valid readout payload', () => {
    const result = readoutPayloadSchema.safeParse(makeValidPayload());
    expect(result.success).toBe(true);
  });

  it('rejects payload missing required video_id', () => {
    const { video_id: _, ...noVideoId } = makeValidPayload();
    const result = readoutPayloadSchema.safeParse(noVideoId);
    expect(result.success).toBe(false);
  });

  it('rejects payload missing required aggregate', () => {
    const { aggregate: _, ...noAggregate } = makeValidPayload();
    const result = readoutPayloadSchema.safeParse(noAggregate);
    expect(result.success).toBe(false);
  });

  it('rejects negative video_time_ms in trace points', () => {
    const payload = makeValidPayload({
      traces: {
        attention_score: [{ video_time_ms: -100, value: 50 }],
        attention_velocity: [],
        blink_rate: [],
        blink_inhibition: [],
        reward_proxy: [],
        valence_proxy: [],
        arousal_proxy: [],
        novelty_proxy: [],
        tracking_confidence: []
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  it('accepts null trace values', () => {
    const payload = makeValidPayload({
      traces: {
        attention_score: [{ video_time_ms: 0, value: null }],
        attention_velocity: [],
        blink_rate: [],
        blink_inhibition: [],
        reward_proxy: [],
        valence_proxy: [],
        arousal_proxy: [],
        novelty_proxy: [],
        tracking_confidence: []
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
  });

  it('validates annotation marker types', () => {
    const validTypes = ['engaging_moment', 'confusing_moment', 'stop_watching_moment', 'cta_landed_moment'];
    const payload = makeValidPayload({
      labels: {
        annotations: validTypes.map((type) => ({
          id: `ann-${type}`,
          session_id: 'sess-1',
          video_id: 'test',
          marker_type: type,
          video_time_ms: 1000,
          note: null,
          created_at: '2026-01-01T00:00:00Z'
        }))
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
  });

  it('rejects invalid annotation marker type', () => {
    const payload = makeValidPayload({
      labels: {
        annotations: [{
          id: 'ann-1',
          session_id: 'sess-1',
          video_id: 'test',
          marker_type: 'invalid_type',
          video_time_ms: 1000,
          note: null,
          created_at: '2026-01-01T00:00:00Z'
        }]
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  it('validates AU channel requires non-empty au_name', () => {
    const payload = makeValidPayload({
      traces: {
        attention_score: [],
        attention_velocity: [],
        blink_rate: [],
        blink_inhibition: [],
        reward_proxy: [],
        valence_proxy: [],
        arousal_proxy: [],
        novelty_proxy: [],
        tracking_confidence: [],
        au_channels: [{
          au_name: '',  // Invalid — min length 1
          points: []
        }]
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  it('accepts valid AU channels', () => {
    const payload = makeValidPayload({
      traces: {
        attention_score: [],
        attention_velocity: [],
        blink_rate: [],
        blink_inhibition: [],
        reward_proxy: [],
        valence_proxy: [],
        arousal_proxy: [],
        novelty_proxy: [],
        tracking_confidence: [],
        au_channels: [{
          au_name: 'AU06',
          points: [{ video_time_ms: 0, value: 0.7 }]
        }]
      }
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
  });

  it('accepts optional neuro_scores and product_rollups as null', () => {
    const payload = makeValidPayload({
      neuro_scores: null,
      product_rollups: null
    });

    const result = readoutPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
  });
});
