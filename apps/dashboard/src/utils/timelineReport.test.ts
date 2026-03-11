import { describe, it, expect } from 'vitest';
import {
  TRACK_ORDER,
  DEFAULT_TIMELINE_TRACK_VISIBILITY,
  buildTimelineTracks,
  buildTimelineKeyMoments
} from './timelineReport';
import type { VideoReadout, ReadoutSegment } from '../types';
import type { TimelineTrackKey } from './timelineReport';

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
      attention_score: [],
      attention_velocity: [],
      blink_rate: [],
      blink_inhibition: [],
      reward_proxy: [],
      valence_proxy: [],
      arousal_proxy: [],
      novelty_proxy: [],
      tracking_confidence: [],
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

// ---------------------------------------------------------------------------
// TRACK_ORDER
// ---------------------------------------------------------------------------

describe('TRACK_ORDER', () => {
  it('contains exactly 8 track keys', () => {
    expect(TRACK_ORDER).toHaveLength(8);
  });

  it('contains all expected keys', () => {
    const expected: TimelineTrackKey[] = [
      'attention_arrest',
      'attentional_synchrony',
      'narrative_control',
      'blink_transport',
      'reward_anticipation',
      'boundary_encoding',
      'cta_reception',
      'au_friction'
    ];
    expect(TRACK_ORDER).toEqual(expected);
  });
});

// ---------------------------------------------------------------------------
// DEFAULT_TIMELINE_TRACK_VISIBILITY
// ---------------------------------------------------------------------------

describe('DEFAULT_TIMELINE_TRACK_VISIBILITY', () => {
  it('has an entry for each track key', () => {
    for (const key of TRACK_ORDER) {
      expect(DEFAULT_TIMELINE_TRACK_VISIBILITY).toHaveProperty(key);
    }
  });

  it('all tracks default to true', () => {
    for (const key of TRACK_ORDER) {
      expect(DEFAULT_TIMELINE_TRACK_VISIBILITY[key]).toBe(true);
    }
  });
});

// ---------------------------------------------------------------------------
// buildTimelineTracks
// ---------------------------------------------------------------------------

describe('buildTimelineTracks', () => {
  it('returns 8 tracks in TRACK_ORDER', () => {
    const readout = makeMinimalReadout();
    const tracks = buildTimelineTracks(readout);
    expect(tracks).toHaveLength(8);
    expect(tracks.map((t) => t.key)).toEqual(TRACK_ORDER);
  });

  it('each track has all required fields', () => {
    const readout = makeMinimalReadout();
    const tracks = buildTimelineTracks(readout);
    for (const track of tracks) {
      expect(track).toHaveProperty('key');
      expect(track).toHaveProperty('machineName');
      expect(track).toHaveProperty('label');
      expect(track).toHaveProperty('description');
      expect(track).toHaveProperty('color');
      expect(track).toHaveProperty('windows');
      expect(typeof track.label).toBe('string');
      expect(typeof track.description).toBe('string');
      expect(track.color).toMatch(/^#/);
    }
  });

  it('returns empty windows for minimal readout with no data', () => {
    const readout = makeMinimalReadout();
    const tracks = buildTimelineTracks(readout);
    for (const track of tracks) {
      expect(track.windows).toEqual([]);
    }
  });

  it('populates attention_arrest windows from golden_scenes', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [
          makeSegment({ start_video_time_ms: 2000, end_video_time_ms: 5000, reason_codes: ['High engagement'] })
        ],
        dead_zones: [],
        confusion_segments: []
      }
    });
    const tracks = buildTimelineTracks(readout);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    expect(arrestTrack.windows.length).toBeGreaterThanOrEqual(1);
    expect(arrestTrack.windows[0].source).toBe('segments.golden_scenes');
  });

  it('populates attention_arrest windows from dead_zones', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 5000, end_video_time_ms: 10000, reason_codes: ['Drop-off risk'] })
        ],
        confusion_segments: []
      }
    });
    const tracks = buildTimelineTracks(readout);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    expect(arrestTrack.windows.length).toBeGreaterThanOrEqual(1);
    expect(arrestTrack.windows[0].source).toBe('segments.dead_zones');
  });

  it('populates cta_reception windows from cta_markers', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 10000, label: 'Buy now' }
        ]
      }
    });
    const tracks = buildTimelineTracks(readout);
    const ctaTrack = tracks.find((t) => t.key === 'cta_reception')!;
    expect(ctaTrack.windows.length).toBeGreaterThanOrEqual(1);
    expect(ctaTrack.windows[0].source).toBe('context.cta_markers');
    expect(ctaTrack.windows[0].reason).toContain('Buy now');
  });

  it('populates au_friction windows from confusion_segments', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [],
        confusion_segments: [
          makeSegment({ start_video_time_ms: 3000, end_video_time_ms: 6000, reason_codes: ['Confusion spike'] })
        ]
      }
    });
    const tracks = buildTimelineTracks(readout);
    const frictionTrack = tracks.find((t) => t.key === 'au_friction')!;
    expect(frictionTrack.windows.length).toBeGreaterThanOrEqual(1);
    expect(frictionTrack.windows[0].source).toBe('segments.confusion_segments');
  });

  it('deduplicates identical windows', () => {
    const seg = makeSegment({ start_video_time_ms: 2000, end_video_time_ms: 5000 });
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [seg, { ...seg }],
        dead_zones: [],
        confusion_segments: []
      }
    });
    const tracks = buildTimelineTracks(readout);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    // Should be deduplicated to just 1
    expect(arrestTrack.windows).toHaveLength(1);
  });

  it('sorts windows by start_ms then end_ms', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [
          makeSegment({ start_video_time_ms: 10000, end_video_time_ms: 15000, reason_codes: ['B'] }),
          makeSegment({ start_video_time_ms: 2000, end_video_time_ms: 5000, reason_codes: ['A'] })
        ],
        dead_zones: [],
        confusion_segments: []
      }
    });
    const tracks = buildTimelineTracks(readout);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    if (arrestTrack.windows.length >= 2) {
      expect(arrestTrack.windows[0].start_ms).toBeLessThanOrEqual(arrestTrack.windows[1].start_ms);
    }
  });

  it('populates neuro_scores evidence windows', () => {
    const readout = makeMinimalReadout({
      neuro_scores: {
        model_version: '1.0',
        generated_at: '2026-01-01',
        scores: {
          arrest_score: {
            machine_name: 'arrest_score',
            display_name: 'Arrest',
            scalar_value: 75,
            confidence: 0.8,
            evidence_windows: [
              { start_ms: 1000, end_ms: 3000, reason: 'Neuro evidence window' }
            ],
            pathway: 'attention',
            color: '#2f7dff'
          }
        }
      } as any
    });
    const tracks = buildTimelineTracks(readout);
    const arrestTrack = tracks.find((t) => t.key === 'attention_arrest')!;
    expect(arrestTrack.windows.length).toBeGreaterThanOrEqual(1);
    expect(arrestTrack.windows[0].source).toBe('neuro_score_contract');
  });
});

// ---------------------------------------------------------------------------
// buildTimelineKeyMoments
// ---------------------------------------------------------------------------

describe('buildTimelineKeyMoments', () => {
  it('returns hook_window even for minimal readout', () => {
    const readout = makeMinimalReadout();
    const moments = buildTimelineKeyMoments(readout);
    const hooks = moments.filter((m) => m.type === 'hook_window');
    expect(hooks).toHaveLength(1);
    expect(hooks[0].start_ms).toBe(0);
    expect(hooks[0].end_ms).toBeLessThanOrEqual(3000);
  });

  it('uses hook_strength diagnostic card when available', () => {
    const readout = makeMinimalReadout({
      diagnostics: [
        {
          card_type: 'hook_strength',
          start_video_time_ms: 0,
          end_video_time_ms: 2500,
          primary_metric: 'attention_score',
          primary_metric_value: 85,
          why_flagged: 'Strong opening engagement',
          reason_codes: ['strong_hook'],
          confidence: 0.9
        }
      ]
    });
    const moments = buildTimelineKeyMoments(readout);
    const hook = moments.find((m) => m.type === 'hook_window')!;
    expect(hook.reason).toBe('Strong opening engagement');
  });

  it('creates event_boundary moments for scenes starting after 0', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [
          { scene_index: 0, start_ms: 0, end_ms: 5000, label: 'Intro' },
          { scene_index: 1, start_ms: 5000, end_ms: 10000, label: 'Main' }
        ],
        cuts: [],
        cta_markers: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    const boundaries = moments.filter((m) => m.type === 'event_boundary');
    // Only scene with start_ms > 0 gets a boundary
    expect(boundaries).toHaveLength(1);
    expect(boundaries[0].reason).toContain('Main');
  });

  it('creates event_boundary moments from cuts', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [
          { cut_id: 'cut-1', start_ms: 3000, end_ms: 3500 }
        ],
        cta_markers: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    const boundaries = moments.filter((m) => m.type === 'event_boundary');
    expect(boundaries.length).toBeGreaterThanOrEqual(1);
    expect(boundaries[0].reason).toContain('cut-1');
  });

  it('creates dead_zone moments from segments', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 8000, end_video_time_ms: 15000, reason_codes: ['Drop-off'] })
        ],
        confusion_segments: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    const deadZones = moments.filter((m) => m.type === 'dead_zone');
    expect(deadZones.length).toBeGreaterThanOrEqual(1);
    expect(deadZones[0].color).toBe('#ef4444');
  });

  it('creates cta_window moments from cta_markers', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 15000, label: 'Subscribe' }
        ]
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    const ctaWindows = moments.filter((m) => m.type === 'cta_window');
    expect(ctaWindows.length).toBeGreaterThanOrEqual(1);
    expect(ctaWindows[0].reason).toContain('Subscribe');
  });

  it('deduplicates identical moments', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 5000, end_video_time_ms: 10000, reason_codes: ['Drop'] }),
          makeSegment({ start_video_time_ms: 5000, end_video_time_ms: 10000, reason_codes: ['Drop'] })
        ],
        confusion_segments: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    const deadZones = moments.filter((m) => m.type === 'dead_zone');
    expect(deadZones).toHaveLength(1);
  });

  it('sorts moments by start_ms then end_ms', () => {
    const readout = makeMinimalReadout({
      context: {
        scenes: [
          { scene_index: 0, start_ms: 0, end_ms: 5000 },
          { scene_index: 1, start_ms: 5000, end_ms: 10000 },
          { scene_index: 2, start_ms: 10000, end_ms: 20000 }
        ],
        cuts: [],
        cta_markers: [
          { cta_id: 'cta1', video_time_ms: 3000 }
        ]
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    for (let i = 1; i < moments.length; i++) {
      const prev = moments[i - 1];
      const curr = moments[i];
      expect(
        prev.start_ms < curr.start_ms ||
        (prev.start_ms === curr.start_ms && prev.end_ms <= curr.end_ms)
      ).toBe(true);
    }
  });

  it('normalizes windows to be within [0, durationMs]', () => {
    const readout = makeMinimalReadout({
      duration_ms: 10000,
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 9500, end_video_time_ms: 12000 })
        ],
        confusion_segments: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    moments.forEach((m) => {
      expect(m.start_ms).toBeGreaterThanOrEqual(0);
      expect(m.end_ms).toBeLessThanOrEqual(10000);
    });
  });

  it('each moment has a color from the KEY_MOMENT_COLORS map', () => {
    const readout = makeMinimalReadout({
      segments: {
        attention_gain_segments: [],
        attention_loss_segments: [],
        golden_scenes: [],
        dead_zones: [
          makeSegment({ start_video_time_ms: 5000, end_video_time_ms: 10000 })
        ],
        confusion_segments: []
      }
    });
    const moments = buildTimelineKeyMoments(readout);
    moments.forEach((m) => {
      expect(m.color).toMatch(/^#[0-9a-f]{6}$/i);
    });
  });
});
