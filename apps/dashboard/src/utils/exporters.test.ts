import { describe, it, expect } from 'vitest';
import {
  buildReadoutCsv,
  buildReadoutJsonPayload,
  buildEditSuggestionsStubPayload
} from './exporters';
import type { VideoReadout, ReadoutSegment } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSegment(overrides: Partial<ReadoutSegment> = {}): ReadoutSegment {
  return {
    start_video_time_ms: 0,
    end_video_time_ms: 1000,
    metric: 'attention_score',
    magnitude: 0.7,
    confidence: 0.8,
    reason_codes: ['test_reason'],
    ...overrides
  };
}

function makeMinimalReadout(overrides: Partial<VideoReadout> = {}): VideoReadout {
  return {
    schema_version: '2.0.0',
    video_id: 'test-video',
    aggregate: true,
    duration_ms: 30000,
    timebase: { window_ms: 1000, step_ms: 500 },
    context: {
      scenes: [],
      cuts: [],
      cta_markers: []
    },
    traces: {
      attention_score: [
        { video_time_ms: 0, value: 50 },
        { video_time_ms: 1000, value: 60 }
      ],
      attention_velocity: [
        { video_time_ms: 0, value: 0 },
        { video_time_ms: 1000, value: 5 }
      ],
      blink_rate: [
        { video_time_ms: 0, value: 0.3 },
        { video_time_ms: 1000, value: 0.25 }
      ],
      blink_inhibition: [
        { video_time_ms: 0, value: 10 },
        { video_time_ms: 1000, value: 15 }
      ],
      reward_proxy: [
        { video_time_ms: 0, value: 40 },
        { video_time_ms: 1000, value: 55 }
      ],
      valence_proxy: [
        { video_time_ms: 0, value: 45 },
        { video_time_ms: 1000, value: 50 }
      ],
      arousal_proxy: [
        { video_time_ms: 0, value: 30 },
        { video_time_ms: 1000, value: 35 }
      ],
      novelty_proxy: [
        { video_time_ms: 0, value: 20 },
        { video_time_ms: 1000, value: 25 }
      ],
      tracking_confidence: [
        { video_time_ms: 0, value: 0.95 },
        { video_time_ms: 1000, value: 0.9 }
      ],
      au_channels: []
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
        sessions_count: 1,
        participants_count: 1,
        total_trace_points: 100,
        face_ok_rate: 0.95,
        mean_brightness: 120,
        low_confidence_windows: 0
      },
      low_confidence_windows: []
    },
    ...overrides
  };
}

const FIXED_OPTIONS = { generatedAt: '2026-01-15T12:00:00.000Z' };

// ---------------------------------------------------------------------------
// buildReadoutCsv
// ---------------------------------------------------------------------------

describe('buildReadoutCsv', () => {
  it('produces a string with header + data rows', () => {
    const readout = makeMinimalReadout();
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    const lines = csv.split('\n');
    // Header + at least 1 data row
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });

  it('header row contains expected standard columns', () => {
    const readout = makeMinimalReadout();
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    const headerLine = csv.split('\n')[0];
    expect(headerLine).toContain('schema_version');
    expect(headerLine).toContain('video_id');
    expect(headerLine).toContain('attention_score');
    expect(headerLine).toContain('reward_proxy');
    expect(headerLine).toContain('blink_rate');
    expect(headerLine).toContain('tracking_confidence');
  });

  it('includes AU columns when selectedAuNames are provided', () => {
    const readout = makeMinimalReadout();
    const csv = buildReadoutCsv(readout, ['AU12', 'AU06'], FIXED_OPTIONS);
    const headerLine = csv.split('\n')[0];
    expect(headerLine).toContain('au_AU12');
    expect(headerLine).toContain('au_AU06');
  });

  it('cells are properly quoted for CSV safety', () => {
    const readout = makeMinimalReadout();
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    const lines = csv.split('\n');
    // Every cell should be quoted
    lines.forEach((line) => {
      const cells = line.match(/"[^"]*(?:""[^"]*)*"/g);
      expect(cells).not.toBeNull();
    });
  });

  it('handles null values gracefully (empty string cells)', () => {
    const readout = makeMinimalReadout({
      traces: {
        attention_score: [{ video_time_ms: 0, value: null }],
        attention_velocity: [{ video_time_ms: 0, value: null }],
        blink_rate: [{ video_time_ms: 0, value: null }],
        blink_inhibition: [{ video_time_ms: 0, value: null }],
        reward_proxy: [{ video_time_ms: 0, value: null }],
        valence_proxy: [{ video_time_ms: 0, value: null }],
        arousal_proxy: [{ video_time_ms: 0, value: null }],
        novelty_proxy: [{ video_time_ms: 0, value: null }],
        tracking_confidence: [{ video_time_ms: 0, value: null }],
        au_channels: []
      }
    });
    // Should not throw
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    expect(csv).toBeTruthy();
  });

  it('includes metadata in each data row', () => {
    const readout = makeMinimalReadout();
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    const dataLines = csv.split('\n').slice(1);
    dataLines.forEach((line) => {
      expect(line).toContain('test-video');
      expect(line).toContain('2.0.0');
    });
  });

  it('escapes double quotes inside cell values', () => {
    const readout = makeMinimalReadout({ video_id: 'vid"test' });
    const csv = buildReadoutCsv(readout, [], FIXED_OPTIONS);
    // Escaped as "" inside the cell
    expect(csv).toContain('vid""test');
  });
});

// ---------------------------------------------------------------------------
// buildReadoutJsonPayload
// ---------------------------------------------------------------------------

describe('buildReadoutJsonPayload', () => {
  it('returns object with all top-level keys', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload).toHaveProperty('schema_version');
    expect(payload).toHaveProperty('metadata');
    expect(payload).toHaveProperty('context');
    expect(payload).toHaveProperty('segments');
    expect(payload).toHaveProperty('labels');
    expect(payload).toHaveProperty('quality');
    expect(payload).toHaveProperty('diagnostics');
    expect(payload).toHaveProperty('aggregate_metrics');
    expect(payload).toHaveProperty('neuro_scores');
    expect(payload).toHaveProperty('product_rollups');
    expect(payload).toHaveProperty('legacy_score_adapters');
  });

  it('metadata contains video_id and duration_ms', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.metadata.video_id).toBe('test-video');
    expect(payload.metadata.duration_ms).toBe(30000);
    expect(payload.metadata.generated_at).toBe('2026-01-15T12:00:00.000Z');
  });

  it('defaults optional fields to null when absent', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.metadata.variant_id).toBeNull();
    expect(payload.metadata.session_id).toBeNull();
    expect(payload.aggregate_metrics).toBeNull();
    expect(payload.neuro_scores).toBeNull();
    expect(payload.product_rollups).toBeNull();
  });

  it('defaults diagnostics to empty array when absent', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.diagnostics).toEqual([]);
  });

  it('defaults legacy_score_adapters to empty array when absent', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.legacy_score_adapters).toEqual([]);
  });

  it('labels defaults annotation_summary and survey_summary to null', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.labels.annotation_summary).toBeNull();
    expect(payload.labels.survey_summary).toBeNull();
  });

  it('preserves context data', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [{ scene_index: 0, start_ms: 0, end_ms: 5000, label: 'Intro' }],
        cuts: [],
        cta_markers: []
      }
    });
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.context.scenes).toHaveLength(1);
    expect(payload.context.scenes[0].label).toBe('Intro');
  });

  it('metadata timebase reflects readout timebase', () => {
    const readout = makeMinimalReadout();
    const payload = buildReadoutJsonPayload(readout, FIXED_OPTIONS);
    expect(payload.metadata.timebase.window_ms).toBe(1000);
    expect(payload.metadata.timebase.step_ms).toBe(500);
  });
});

// ---------------------------------------------------------------------------
// buildEditSuggestionsStubPayload
// ---------------------------------------------------------------------------

describe('buildEditSuggestionsStubPayload', () => {
  it('returns expected top-level structure', () => {
    const readout = makeMinimalReadout();
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload).toHaveProperty('schema_version');
    expect(payload).toHaveProperty('metadata');
    expect(payload).toHaveProperty('edit_suggestions');
    expect(payload.edit_suggestions).toHaveProperty('candidate_trims');
    expect(payload.edit_suggestions).toHaveProperty('candidate_reorder_suggestions');
    expect(payload.edit_suggestions).toHaveProperty('cta_timing_suggestion');
  });

  it('candidate_trims mirrors dead_zones from readout', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 5000, end_video_time_ms: 10000, reason_codes: ['Drop-off'] })
        ],
        confusion_segments: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload.edit_suggestions.candidate_trims).toHaveLength(1);
    expect(payload.edit_suggestions.candidate_trims[0].start_video_time_ms).toBe(5000);
    expect(payload.edit_suggestions.candidate_trims[0].source_metric).toBe('dead_zone');
  });

  it('empty dead_zones → empty candidate_trims', () => {
    const readout = makeMinimalReadout();
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload.edit_suggestions.candidate_trims).toEqual([]);
  });

  it('generates reorder suggestion when top golden scene is after first scene', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [
          { scene_index: 0, start_ms: 0, end_ms: 5000 },
          { scene_index: 1, start_ms: 5000, end_ms: 10000 }
        ],
        cuts: [],
        cta_markers: []
      },
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [
          makeSegment({ start_video_time_ms: 6000, end_video_time_ms: 9000, magnitude: 0.95 })
        ],
        dead_zones: [],
        confusion_segments: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload.edit_suggestions.candidate_reorder_suggestions).toHaveLength(1);
    expect(payload.edit_suggestions.candidate_reorder_suggestions[0].current_start_video_time_ms).toBe(6000);
    expect(payload.edit_suggestions.candidate_reorder_suggestions[0].suggested_target_start_video_time_ms).toBe(0);
  });

  it('no reorder suggestion when golden scene is in opening window', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [
          { scene_index: 0, start_ms: 0, end_ms: 5000 }
        ],
        cuts: [],
        cta_markers: []
      },
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [
          makeSegment({ start_video_time_ms: 1000, end_video_time_ms: 4000, magnitude: 0.95 })
        ],
        dead_zones: [],
        confusion_segments: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload.edit_suggestions.candidate_reorder_suggestions).toEqual([]);
  });

  it('CTA timing: alignment "unknown" when no CTA marker exists', () => {
    const readout = makeMinimalReadout();
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    expect(payload.edit_suggestions.cta_timing_suggestion).not.toBeNull();
    expect(payload.edit_suggestions.cta_timing_suggestion!.alignment).toBe('unknown');
  });

  it('CTA timing: alignment "near_peak" when CTA is close to reward peak', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 1000 }
        ]
      },
      traces: {
        attention_score: [{ video_time_ms: 0, value: 50 }, { video_time_ms: 1000, value: 60 }],
        attention_velocity: [{ video_time_ms: 0, value: 0 }, { video_time_ms: 1000, value: 5 }],
        blink_rate: [{ video_time_ms: 0, value: 0.3 }, { video_time_ms: 1000, value: 0.25 }],
        blink_inhibition: [{ video_time_ms: 0, value: 10 }, { video_time_ms: 1000, value: 15 }],
        reward_proxy: [
          { video_time_ms: 0, value: 40 },
          { video_time_ms: 1000, value: 80 }
        ],
        valence_proxy: [{ video_time_ms: 0, value: 45 }, { video_time_ms: 1000, value: 50 }],
        arousal_proxy: [{ video_time_ms: 0, value: 30 }, { video_time_ms: 1000, value: 35 }],
        novelty_proxy: [{ video_time_ms: 0, value: 20 }, { video_time_ms: 1000, value: 25 }],
        tracking_confidence: [{ video_time_ms: 0, value: 0.95 }, { video_time_ms: 1000, value: 0.9 }],
        au_channels: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    // CTA at 1000ms, reward peak at 1000ms → near_peak
    expect(payload.edit_suggestions.cta_timing_suggestion!.alignment).toBe('near_peak');
  });

  it('CTA timing: alignment "post_peak" when CTA is after reward peak', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 20000 }
        ]
      },
      traces: {
        attention_score: [{ video_time_ms: 0, value: 50 }, { video_time_ms: 5000, value: 60 }],
        attention_velocity: [{ video_time_ms: 0, value: 0 }, { video_time_ms: 5000, value: 5 }],
        blink_rate: [{ video_time_ms: 0, value: 0.3 }, { video_time_ms: 5000, value: 0.25 }],
        blink_inhibition: [{ video_time_ms: 0, value: 10 }, { video_time_ms: 5000, value: 15 }],
        reward_proxy: [
          { video_time_ms: 0, value: 40 },
          { video_time_ms: 5000, value: 90 }
        ],
        valence_proxy: [{ video_time_ms: 0, value: 45 }, { video_time_ms: 5000, value: 50 }],
        arousal_proxy: [{ video_time_ms: 0, value: 30 }, { video_time_ms: 5000, value: 35 }],
        novelty_proxy: [{ video_time_ms: 0, value: 20 }, { video_time_ms: 5000, value: 25 }],
        tracking_confidence: [{ video_time_ms: 0, value: 0.95 }, { video_time_ms: 5000, value: 0.9 }],
        au_channels: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    // CTA at 20000ms, reward peak at 5000ms → post_peak
    expect(payload.edit_suggestions.cta_timing_suggestion!.alignment).toBe('post_peak');
  });

  it('CTA timing: alignment "pre_peak" when CTA is before reward peak', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 2000 }
        ]
      },
      traces: {
        attention_score: [{ video_time_ms: 0, value: 50 }, { video_time_ms: 20000, value: 60 }],
        attention_velocity: [{ video_time_ms: 0, value: 0 }, { video_time_ms: 20000, value: 5 }],
        blink_rate: [{ video_time_ms: 0, value: 0.3 }, { video_time_ms: 20000, value: 0.25 }],
        blink_inhibition: [{ video_time_ms: 0, value: 10 }, { video_time_ms: 20000, value: 15 }],
        reward_proxy: [
          { video_time_ms: 0, value: 40 },
          { video_time_ms: 20000, value: 90 }
        ],
        valence_proxy: [{ video_time_ms: 0, value: 45 }, { video_time_ms: 20000, value: 50 }],
        arousal_proxy: [{ video_time_ms: 0, value: 30 }, { video_time_ms: 20000, value: 35 }],
        novelty_proxy: [{ video_time_ms: 0, value: 20 }, { video_time_ms: 20000, value: 25 }],
        tracking_confidence: [{ video_time_ms: 0, value: 0.95 }, { video_time_ms: 20000, value: 0.9 }],
        au_channels: []
      }
    });
    const payload = buildEditSuggestionsStubPayload(readout, FIXED_OPTIONS);
    // CTA at 2000ms, reward peak at 20000ms → pre_peak
    expect(payload.edit_suggestions.cta_timing_suggestion!.alignment).toBe('pre_peak');
  });
});
