import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { readoutPayloadSchema } from '../src/schemas/readoutPayload';

const neuroScoreTaxonomyFixturePath = new URL(
  '../../../fixtures/neuro_score_taxonomy.sample.json',
  import.meta.url
);
const neuroScoreTaxonomyFixture = JSON.parse(readFileSync(neuroScoreTaxonomyFixturePath, 'utf-8'));

const readoutPayloadLegacy = {
  video_id: 'demo-video',
  duration_ms: 9000,
  scenes: [
    { scene_index: 0, start_ms: 0, end_ms: 3000, label: 'Intro', scene_id: 'scene-1', cut_id: 'cut-1' },
    {
      scene_index: 1,
      start_ms: 3000,
      end_ms: 6000,
      label: 'Middle',
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main'
    },
    { scene_index: 2, start_ms: 6000, end_ms: 9000, label: 'Finale', scene_id: 'scene-3', cut_id: 'cut-3' }
  ],
  cuts: [
    { cut_id: 'cut-1', start_ms: 0, end_ms: 3000, scene_id: 'scene-1' },
    { cut_id: 'cut-2', start_ms: 3000, end_ms: 6000, scene_id: 'scene-2', cta_id: 'cta-main' },
    { cut_id: 'cut-3', start_ms: 6000, end_ms: 9000, scene_id: 'scene-3' }
  ],
  cta_markers: [
    {
      cta_id: 'cta-main',
      video_time_ms: 4200,
      start_ms: 3900,
      end_ms: 5000,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      label: 'Main CTA'
    }
  ],
  traces: {
    attention_score: [
      { video_time_ms: 0, value: 42, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 48, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 59, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 52, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 38, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 34, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 45, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 64, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 72, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    attention_velocity: [
      { video_time_ms: 0, value: 0, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 6, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 8, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: -5, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: -8, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: -4, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 6, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 10, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 7, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    blink_rate: [
      { video_time_ms: 0, value: 0.1, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.12, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.09, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 0.3, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 0.45, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 0.42, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 0.18, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 0.1, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 0.08, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    blink_inhibition: [
      { video_time_ms: 0, value: 0.22, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.28, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.3, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: -0.1, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: -0.22, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: -0.25, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 0.1, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 0.24, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 0.32, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    reward_proxy: [
      { video_time_ms: 0, value: 45, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 52, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 64, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 48, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 35, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 30, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 50, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 72, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 84, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    tracking_confidence: [
      { video_time_ms: 0, value: 0.86, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.82, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.78, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 0.44, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 0.39, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 0.41, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 0.7, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 0.78, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 0.81, scene_id: 'scene-3', cut_id: 'cut-3' }
    ],
    au_channels: [
      {
        au_name: 'AU04',
        points: [
          { video_time_ms: 0, value: 0.02 },
          { video_time_ms: 1000, value: 0.03 },
          { video_time_ms: 2000, value: 0.02 },
          { video_time_ms: 3000, value: 0.08 },
          { video_time_ms: 4000, value: 0.12 },
          { video_time_ms: 5000, value: 0.1 },
          { video_time_ms: 6000, value: 0.05 },
          { video_time_ms: 7000, value: 0.03 },
          { video_time_ms: 8000, value: 0.02 }
        ]
      },
      {
        au_name: 'AU06',
        points: [
          { video_time_ms: 0, value: 0.05 },
          { video_time_ms: 1000, value: 0.07 },
          { video_time_ms: 2000, value: 0.1 },
          { video_time_ms: 3000, value: 0.03 },
          { video_time_ms: 4000, value: 0.02 },
          { video_time_ms: 5000, value: 0.02 },
          { video_time_ms: 6000, value: 0.08 },
          { video_time_ms: 7000, value: 0.12 },
          { video_time_ms: 8000, value: 0.15 }
        ]
      },
      {
        au_name: 'AU12',
        points: [
          { video_time_ms: 0, value: 0.08 },
          { video_time_ms: 1000, value: 0.11 },
          { video_time_ms: 2000, value: 0.16 },
          { video_time_ms: 3000, value: 0.04 },
          { video_time_ms: 4000, value: 0.01 },
          { video_time_ms: 5000, value: 0.02 },
          { video_time_ms: 6000, value: 0.12 },
          { video_time_ms: 7000, value: 0.18 },
          { video_time_ms: 8000, value: 0.23 }
        ]
      }
    ]
  },
  segments: {
    attention_gain_segments: [
      {
        start_video_time_ms: 1000,
        end_video_time_ms: 3000,
        metric: 'attention_gain',
        magnitude: 7.8,
        confidence: 0.82,
        reason_codes: ['above_local_baseline', 'upward_velocity'],
        scene_id: 'scene-1'
      }
    ],
    attention_loss_segments: [
      {
        start_video_time_ms: 3000,
        end_video_time_ms: 5000,
        metric: 'attention_loss',
        magnitude: 8.1,
        confidence: 0.44,
        reason_codes: ['below_local_baseline', 'downward_velocity'],
        scene_id: 'scene-2'
      }
    ],
    golden_scenes: [
      {
        start_video_time_ms: 7000,
        end_video_time_ms: 8000,
        metric: 'golden_scene',
        magnitude: 78,
        confidence: 0.79,
        reason_codes: ['high_reward_proxy', 'high_attention_score'],
        scene_id: 'scene-3'
      }
    ],
    dead_zones: [
      {
        start_video_time_ms: 3000,
        end_video_time_ms: 5000,
        metric: 'dead_zone',
        magnitude: 12,
        confidence: 0.41,
        reason_codes: ['sustained_attention_drop', 'low_tracking_confidence'],
        scene_id: 'scene-2'
      }
    ],
    confusion_segments: [
      {
        start_video_time_ms: 3000,
        end_video_time_ms: 5000,
        metric: 'confusion_segment',
        magnitude: 2.4,
        confidence: 0.43,
        reason_codes: ['elevated_blink_rate', 'au4_friction_proxy'],
        scene_id: 'scene-2'
      }
    ]
  },
  diagnostics: [
    {
      card_type: 'golden_scene',
      scene_index: 2,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      scene_label: 'Finale',
      scene_thumbnail_url: null,
      start_video_time_ms: 7000,
      end_video_time_ms: 8000,
      primary_metric: 'reward_proxy',
      primary_metric_value: 78,
      why_flagged: 'Highest sustained reward proxy with strong attention retention in this scene.',
      confidence: 0.79,
      reason_codes: ['high_reward_proxy', 'attention_retention']
    },
    {
      card_type: 'hook_strength',
      scene_index: 0,
      scene_id: 'scene-1',
      cut_id: 'cut-1',
      cta_id: null,
      scene_label: 'Intro',
      scene_thumbnail_url: null,
      start_video_time_ms: 0,
      end_video_time_ms: 3000,
      primary_metric: 'hook_strength',
      primary_metric_value: 58.2,
      why_flagged: 'Opening window retained attention well.',
      confidence: 0.82,
      reason_codes: ['opening_window', 'positive_attention_retention']
    },
    {
      card_type: 'cta_receptivity',
      scene_index: 1,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      scene_label: 'Middle',
      scene_thumbnail_url: null,
      start_video_time_ms: 2000,
      end_video_time_ms: 5000,
      primary_metric: 'cta_receptivity',
      primary_metric_value: 51.1,
      why_flagged: 'CTA lead-in and CTA window showed weak response.',
      confidence: 0.56,
      reason_codes: ['cta_lead_in_window', 'cta_on_window']
    },
    {
      card_type: 'attention_drop_scene',
      scene_index: 1,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      scene_label: 'Middle',
      scene_thumbnail_url: null,
      start_video_time_ms: 3000,
      end_video_time_ms: 5000,
      primary_metric: 'attention_drop_magnitude',
      primary_metric_value: 8.1,
      why_flagged: 'Largest sustained negative attention delta observed in this scene.',
      confidence: 0.44,
      reason_codes: ['below_local_baseline', 'downward_velocity']
    },
    {
      card_type: 'confusion_scene',
      scene_index: 1,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      scene_label: 'Middle',
      scene_thumbnail_url: null,
      start_video_time_ms: 3000,
      end_video_time_ms: 5000,
      primary_metric: 'friction_score',
      primary_metric_value: 2.4,
      why_flagged: 'Friction indicators (AU4/blink + falling attention) were elevated in this scene.',
      confidence: 0.43,
      reason_codes: ['elevated_blink_rate', 'au4_friction_proxy']
    },
    {
      card_type: 'recovery_scene',
      scene_index: 2,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      scene_label: 'Finale',
      scene_thumbnail_url: null,
      start_video_time_ms: 6000,
      end_video_time_ms: 8000,
      primary_metric: 'attention_recovery_magnitude',
      primary_metric_value: 10.3,
      why_flagged: 'Attention recovered after the largest drop in this later segment.',
      confidence: 0.78,
      reason_codes: ['above_local_baseline', 'upward_velocity', 'post_drop_recovery']
    }
  ],
  quality_summary: {
    sessions_count: 2,
    participants_count: 2,
    total_trace_points: 18,
    face_ok_rate: 0.91,
    mean_brightness: 48.2,
    mean_tracking_confidence: 0.67,
    mean_quality_score: 0.65,
    low_confidence_windows: 3,
    usable_seconds: 6,
    quality_badge: 'medium',
    trace_source: 'provided'
  },
  playback_telemetry: [
    {
      id: 'telemetry-1',
      session_id: 'session-a',
      video_id: 'demo-video',
      event_type: 'pause',
      video_time_ms: 2400,
      wall_time_ms: 1700000002400,
      client_monotonic_ms: 2400,
      details: { mode: 'first_pass' },
      scene_id: 'scene-1',
      cut_id: 'cut-1',
      cta_id: null,
      created_at: '2026-03-06T01:00:00Z'
    },
    {
      id: 'telemetry-2',
      session_id: 'session-a',
      video_id: 'demo-video',
      event_type: 'seek_end',
      video_time_ms: 5200,
      wall_time_ms: 1700000005200,
      client_monotonic_ms: 5200,
      details: { fromVideoTimeMs: 6100, toVideoTimeMs: 5200 },
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      created_at: '2026-03-06T01:00:02Z'
    },
    {
      id: 'telemetry-3',
      session_id: 'session-b',
      video_id: 'demo-video',
      event_type: 'abandonment',
      video_time_ms: 7300,
      wall_time_ms: 1700000007300,
      client_monotonic_ms: 7300,
      details: { reason: 'user_ended_early', lastVideoTimeMs: 7300 },
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      created_at: '2026-03-06T01:00:05Z'
    }
  ],
  annotations: [
    {
      id: 'annotation-1',
      session_id: 'session-a',
      video_id: 'demo-video',
      marker_type: 'engaging_moment',
      video_time_ms: 1800,
      scene_id: 'scene-1',
      cut_id: 'cut-1',
      cta_id: null,
      note: 'Strong opener',
      created_at: '2026-03-05T12:00:00Z'
    },
    {
      id: 'annotation-2',
      session_id: 'session-b',
      video_id: 'demo-video',
      marker_type: 'engaging_moment',
      video_time_ms: 4100,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      note: 'Peak for second viewer',
      created_at: '2026-03-05T12:00:03Z'
    },
    {
      id: 'annotation-3',
      session_id: 'session-a',
      video_id: 'demo-video',
      marker_type: 'confusing_moment',
      video_time_ms: 7100,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      note: 'Final transition',
      created_at: '2026-03-05T12:00:05Z'
    },
    {
      id: 'annotation-4',
      session_id: 'session-b',
      video_id: 'demo-video',
      marker_type: 'stop_watching_moment',
      video_time_ms: 7300,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      note: 'Drop-off',
      created_at: '2026-03-05T12:00:08Z'
    },
    {
      id: 'annotation-5',
      session_id: 'session-a',
      video_id: 'demo-video',
      marker_type: 'cta_landed_moment',
      video_time_ms: 5200,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      note: 'CTA understood',
      created_at: '2026-03-05T12:00:10Z'
    }
  ],
  annotation_summary: {
    total_annotations: 5,
    engaging_moment_count: 2,
    confusing_moment_count: 1,
    stop_watching_moment_count: 1,
    cta_landed_moment_count: 1,
    marker_density: [
      {
        marker_type: 'engaging_moment',
        video_time_ms: 4000,
        count: 2,
        density: 1.0,
        scene_id: 'scene-2',
        cut_id: 'cut-2',
        cta_id: 'cta-main'
      },
      {
        marker_type: 'cta_landed_moment',
        video_time_ms: 5000,
        count: 1,
        density: 0.5,
        scene_id: 'scene-2',
        cut_id: 'cut-2',
        cta_id: 'cta-main'
      },
      {
        marker_type: 'confusing_moment',
        video_time_ms: 7000,
        count: 1,
        density: 0.5,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null
      },
      {
        marker_type: 'stop_watching_moment',
        video_time_ms: 7000,
        count: 1,
        density: 0.5,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null
      }
    ],
    top_engaging_timestamps: [
      {
        video_time_ms: 4000,
        count: 2,
        density: 1.0,
        scene_id: 'scene-2',
        cut_id: 'cut-2',
        cta_id: 'cta-main'
      }
    ],
    top_confusing_timestamps: [
      {
        video_time_ms: 7000,
        count: 1,
        density: 0.5,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null
      }
    ]
  },
  survey_summary: {
    responses_count: 8,
    overall_interest_mean: 3.0,
    recall_comprehension_mean: 3.5,
    desire_to_continue_or_take_action_mean: 4.0,
    comment_count: 2
  }
};

const readoutPayload = {
  ...readoutPayloadLegacy,
  schema_version: '1.0.0',
  variant_id: 'variant-a',
  session_id: null,
  aggregate: true,
  duration_ms: readoutPayloadLegacy.duration_ms,
  timebase: {
    window_ms: 1000,
    step_ms: 1000
  },
  context: {
    scenes: readoutPayloadLegacy.scenes,
    cuts: readoutPayloadLegacy.cuts,
    cta_markers: readoutPayloadLegacy.cta_markers
  },
  traces: {
    ...readoutPayloadLegacy.traces,
    attention_score: readoutPayloadLegacy.traces.attention_score.map((point) => ({
      ...point,
      median: point.value,
      ci_low:
        point.value !== null && point.value !== undefined
          ? Number(Math.max(0, point.value - 4).toFixed(6))
          : null,
      ci_high:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, point.value + 4).toFixed(6))
          : null
    })),
    reward_proxy: readoutPayloadLegacy.traces.reward_proxy.map((point) => ({
      ...point,
      median: point.value,
      ci_low:
        point.value !== null && point.value !== undefined
          ? Number(Math.max(0, point.value - 5).toFixed(6))
          : null,
      ci_high:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, point.value + 5).toFixed(6))
          : null
    })),
    valence_proxy: readoutPayloadLegacy.traces.reward_proxy.map((point) => ({
      ...point,
      value: point.value !== null && point.value !== undefined ? Number((point.value * 0.92).toFixed(6)) : null
    })),
    arousal_proxy: readoutPayloadLegacy.traces.attention_score.map((point, index) => ({
      ...point,
      value:
        point.value !== null && point.value !== undefined
          ? Number(
              Math.min(
                100,
                Math.max(
                  0,
                  point.value * 0.74 +
                    Math.abs(readoutPayloadLegacy.traces.attention_velocity[index]?.value ?? 0) * 1.2
                )
              ).toFixed(6)
            )
          : null
    })),
    novelty_proxy: readoutPayloadLegacy.traces.attention_velocity.map((point) => ({
      ...point,
      value:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, Math.max(0, 20 + Math.abs(point.value) * 7.5)).toFixed(6))
          : null
    }))
  },
  labels: {
    annotations: readoutPayloadLegacy.annotations,
    annotation_summary: readoutPayloadLegacy.annotation_summary,
    survey_summary: readoutPayloadLegacy.survey_summary
  },
  quality: {
    session_quality_summary: readoutPayloadLegacy.quality_summary,
    low_confidence_windows: [
      {
        start_video_time_ms: 3000,
        end_video_time_ms: 6000,
        mean_tracking_confidence: 0.413333,
        quality_flags: ['low_light', 'blur']
      }
    ]
  },
  aggregate_metrics: {
    attention_synchrony: 0.82,
    blink_synchrony: 0.76,
    grip_control_score: 0.79,
    attentional_synchrony: {
      pathway: 'direct_panel_gaze',
      global_score: 81.6,
      confidence: 0.88,
      segment_scores: [
        {
          start_ms: 0,
          end_ms: 3000,
          score: 79.4,
          confidence: 0.85,
          pathway: 'direct_panel_gaze',
          reason: 'Direct panel gaze overlap and aligned attention supported convergence.'
        },
        {
          start_ms: 3000,
          end_ms: 6000,
          score: 84.1,
          confidence: 0.9,
          pathway: 'direct_panel_gaze',
          reason: 'Direct panel gaze overlap and aligned attention supported convergence.'
        },
        {
          start_ms: 6000,
          end_ms: 9000,
          score: 80.7,
          confidence: 0.87,
          pathway: 'direct_panel_gaze',
          reason: 'Direct panel gaze overlap and aligned attention supported convergence.'
        }
      ],
      peaks: [
        {
          start_ms: 3000,
          end_ms: 6000,
          score: 84.1,
          reason: 'Peak convergence window with strongest shared visual focus.'
        }
      ],
      valleys: [
        {
          start_ms: 0,
          end_ms: 3000,
          score: 79.4,
          reason: 'Low-convergence window where viewer focus diverged.'
        }
      ],
      evidence_summary:
        'Direct panel gaze overlap was available and used as the primary pathway, with attention alignment as supporting evidence.',
      signals_used: ['panel_gaze_overlap', 'cross_user_attention_alignment', 'signal_quality_weighting']
    },
    narrative_control: {
      pathway: 'timeline_grammar',
      global_score: 73.8,
      confidence: 0.79,
      scene_scores: [
        {
          start_ms: 0,
          end_ms: 3000,
          score: 71.2,
          confidence: 0.76,
          scene_id: 'scene-1',
          scene_label: 'Intro',
          fragmentation_index: 0.2,
          boundary_density: 0.41,
          motion_continuity: 0.82,
          ordering_pattern: 'context_before_face',
          summary: 'Coherent setup and stable transitions.'
        },
        {
          start_ms: 3000,
          end_ms: 6000,
          score: 59.1,
          confidence: 0.7,
          scene_id: 'scene-2',
          scene_label: 'Middle',
          fragmentation_index: 0.48,
          boundary_density: 0.92,
          motion_continuity: 0.61,
          ordering_pattern: 'balanced',
          summary: 'Mid-scene friction from elevated transition density.'
        },
        {
          start_ms: 6000,
          end_ms: 9000,
          score: 83.6,
          confidence: 0.86,
          scene_id: 'scene-3',
          scene_label: 'Finale',
          fragmentation_index: 0.17,
          boundary_density: 0.38,
          motion_continuity: 0.89,
          ordering_pattern: 'context_before_face',
          summary: 'Payoff scene recovers with coherent reveal pacing.'
        }
      ],
      disruption_penalties: [
        {
          start_ms: 3000,
          end_ms: 4000,
          contribution: -4.2,
          category: 'disruptive_transition',
          reason: 'Transition induced temporary attention drop.',
          scene_id: 'scene-2',
          cut_id: 'cut-2',
          cta_id: 'cta-main'
        }
      ],
      reveal_structure_bonuses: [
        {
          start_ms: 6400,
          end_ms: 7600,
          contribution: 6.1,
          category: 'coherent_reveal',
          reason: 'Reveal timing aligned with attention recovery.',
          scene_id: 'scene-3',
          cut_id: 'cut-3'
        }
      ],
      top_contributing_moments: [
        {
          start_ms: 6400,
          end_ms: 7600,
          contribution: 6.1,
          category: 'coherent_reveal',
          reason: 'Reveal timing aligned with attention recovery.',
          scene_id: 'scene-3',
          cut_id: 'cut-3'
        },
        {
          start_ms: 3000,
          end_ms: 4000,
          contribution: -4.2,
          category: 'disruptive_transition',
          reason: 'Transition induced temporary attention drop.',
          scene_id: 'scene-2',
          cut_id: 'cut-2',
          cta_id: 'cta-main'
        }
      ],
      heuristic_checks: [
        {
          heuristic_key: 'hard_hook_first_1_to_3_seconds',
          passed: true,
          score_delta: 6.0,
          reason: 'Opening hook threshold met.',
          start_ms: 0,
          end_ms: 3000
        },
        {
          heuristic_key: 'cta_not_after_disorienting_transition',
          passed: true,
          score_delta: 4.0,
          reason: 'CTA timing avoided immediate disorienting transition.',
          start_ms: 3900,
          end_ms: 5400
        }
      ],
      evidence_summary:
        'Narrative structure held coherence overall, with one disruptive middle transition offset by a coherent payoff reveal.',
      signals_used: [
        'attention_trace',
        'scene_graph_cuts',
        'cut_cadence',
        'camera_motion_proxy',
        'text_overlay_reveal_windows'
      ]
    },
    reward_anticipation: {
      pathway: 'timeline_dynamics',
      global_score: 76.4,
      confidence: 0.82,
      anticipation_ramps: [
        {
          start_ms: 2000,
          end_ms: 5000,
          score: 79.2,
          confidence: 0.83,
          window_type: 'anticipation_ramp',
          reason: 'Pre-payoff pacing and blink suppression converged before the reveal.',
          ramp_slope: 4.2,
          tension_level: 0.69,
          release_level: 0.74
        }
      ],
      payoff_windows: [
        {
          start_ms: 5000,
          end_ms: 6800,
          score: 81.4,
          confidence: 0.82,
          window_type: 'payoff_window',
          reason: 'Payoff release landed within the expected resolution timing window.',
          reward_delta: 12.1,
          tension_level: 0.69,
          release_level: 0.74
        }
      ],
      warnings: [
        {
          warning_key: 'late_resolution',
          severity: 'medium',
          message: 'Tension appeared to resolve later than the primary payoff window.',
          start_ms: 5000,
          end_ms: 7200,
          metric_value: 2200
        }
      ],
      anticipation_strength: 0.78,
      payoff_release_strength: 0.8,
      tension_release_balance: 0.73,
      evidence_summary:
        'Anticipation ramps and payoff release remained aligned, with one late-resolution timing warning in the closing sequence.',
      signals_used: [
        'reward_proxy_trend',
        'pre_payoff_attention_concentration',
        'blink_suppression_pre_payoff',
        'uncertainty_to_resolution_timing',
        'cut_cadence',
        'audio_intensity_rms'
      ]
    },
    ci_method: 'sem_95',
    included_sessions: 2,
    downweighted_sessions: 0
  }
};

const creatorProductRollupsFixturePath = new URL(
  '../../../fixtures/product_rollups_creator.sample.json',
  import.meta.url
);
const enterpriseProductRollupsFixturePath = new URL(
  '../../../fixtures/product_rollups_enterprise.sample.json',
  import.meta.url
);
const creatorProductRollups = JSON.parse(
  readFileSync(creatorProductRollupsFixturePath, 'utf-8')
);
const enterpriseProductRollups = JSON.parse(
  readFileSync(enterpriseProductRollupsFixturePath, 'utf-8')
);
const readoutPayloadCreatorMode = readoutPayloadSchema.parse({
  ...readoutPayload,
  product_rollups: creatorProductRollups
});
const readoutPayloadEnterpriseMode = readoutPayloadSchema.parse({
  ...readoutPayload,
  product_rollups: enterpriseProductRollups
});

const timelineReportReadoutPayload = readoutPayloadSchema.parse({
  ...readoutPayload,
  neuro_scores: neuroScoreTaxonomyFixture
});

const exportPackagePayload = {
  video_metadata: {
    video_id: 'demo-video',
    study_id: 'study-1',
    study_name: 'Readout Study',
    title: 'Demo Stimulus',
    source_url: 'https://cdn.example.com/demo.mp4',
    duration_ms: 9000,
    variant_id: 'variant-a',
    aggregate: true,
    session_id: null,
    window_ms: 1000,
    generated_at: '2026-03-06T01:00:00Z'
  },
  per_timepoint_csv:
    '"video_time_ms","second","scene_id","cut_id","cta_id","attention_score","attention_velocity","blink_rate","blink_inhibition","reward_proxy","tracking_confidence"\n"0","0.000","scene-1","cut-1","","42.000000","0.000000","0.100000","0.220000","45.000000","0.860000"',
  readout_json: {
    video_metadata: {
      video_id: 'demo-video',
      study_id: 'study-1',
      study_name: 'Readout Study',
      title: 'Demo Stimulus',
      source_url: 'https://cdn.example.com/demo.mp4',
      duration_ms: 9000,
      variant_id: 'variant-a',
      aggregate: true,
      session_id: null,
      window_ms: 1000,
      generated_at: '2026-03-06T01:00:00Z'
    },
    scenes: readoutPayload.scenes,
    cta_markers: readoutPayload.cta_markers,
    segments: readoutPayload.segments,
    diagnostics: readoutPayload.diagnostics,
    reward_proxy_peaks: [
      {
        video_time_ms: 8000,
        reward_proxy: 84,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null,
        tracking_confidence: 0.81
      }
    ],
    quality_summary: readoutPayload.quality_summary,
    annotation_summary: readoutPayload.annotation_summary,
    survey_summary: readoutPayload.survey_summary
  },
  compact_report: {
    video_metadata: {
      video_id: 'demo-video',
      study_id: 'study-1',
      study_name: 'Readout Study',
      title: 'Demo Stimulus',
      source_url: 'https://cdn.example.com/demo.mp4',
      duration_ms: 9000,
      variant_id: 'variant-a',
      aggregate: true,
      session_id: null,
      window_ms: 1000,
      generated_at: '2026-03-06T01:00:00Z'
    },
    scenes: readoutPayload.scenes,
    cta_markers: readoutPayload.cta_markers,
    attention_gain_segments: readoutPayload.segments.attention_gain_segments,
    attention_loss_segments: readoutPayload.segments.attention_loss_segments,
    golden_scenes: readoutPayload.segments.golden_scenes,
    dead_zones: readoutPayload.segments.dead_zones,
    reward_proxy_peaks: [
      {
        video_time_ms: 8000,
        reward_proxy: 84,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null,
        tracking_confidence: 0.81
      }
    ],
    quality_summary: readoutPayload.quality_summary,
    annotation_summary: readoutPayload.annotation_summary,
    survey_summary: readoutPayload.survey_summary,
    highlights: {
      top_reward_proxy_peak: {
        video_time_ms: 8000,
        reward_proxy: 84,
        scene_id: 'scene-3',
        cut_id: 'cut-3',
        cta_id: null,
        tracking_confidence: 0.81
      },
      top_attention_gain_segment: readoutPayload.segments.attention_gain_segments[0],
      top_attention_loss_segment: readoutPayload.segments.attention_loss_segments[0],
      top_golden_scene: readoutPayload.segments.golden_scenes[0],
      top_dead_zone: readoutPayload.segments.dead_zones[0]
    }
  }
};

test('readout payload schema fixture validates', () => {
  const fixturePath = new URL('../../../fixtures/readout_payload.sample.json', import.meta.url);
  const fixture = JSON.parse(readFileSync(fixturePath, 'utf-8'));
  const parsed = readoutPayloadSchema.parse(fixture);
  expect(parsed.schema_version).toBe('1.0.0');
  expect(parsed.traces.reward_proxy.length).toBeGreaterThan(0);
});

test('renders overlays from fixture ReadoutPayload and supports click-to-seek', async ({ page }) => {
  const fixturePath = new URL('../../../fixtures/readout_payload.sample.json', import.meta.url);
  const fixture = readoutPayloadSchema.parse(JSON.parse(readFileSync(fixturePath, 'utf-8')));
  const extendedAttentionScore = [
    ...fixture.traces.attention_score,
    {
      ...fixture.traces.attention_score[fixture.traces.attention_score.length - 1],
      video_time_ms: 3000,
      value: 58,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main'
    },
    {
      ...fixture.traces.attention_score[fixture.traces.attention_score.length - 1],
      video_time_ms: 4000,
      value: 49,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main'
    },
    {
      ...fixture.traces.attention_score[fixture.traces.attention_score.length - 1],
      video_time_ms: 6000,
      value: 63,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null
    },
    {
      ...fixture.traces.attention_score[fixture.traces.attention_score.length - 1],
      video_time_ms: 8000,
      value: 71,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null
    }
  ];
  const fixturePayload = {
    ...fixture,
    video_id: 'demo-video',
    aggregate: false,
    session_id: 'session-fixture',
    traces: {
      ...fixture.traces,
      attention_score: extendedAttentionScore
    }
  };

  await page.unroute('**/videos/demo-video/readout*');
  await page.route('**/videos/demo-video/readout*', async (route) => {
    if (route.request().url().includes('/readout/export-package')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fixturePayload)
    });
  });

  await page.goto('/videos/demo-video');

  const chart = page.getByTestId('summary-chart');
  await expect(chart.getByText('Hook', { exact: true }).first()).toBeVisible();
  await expect(chart.getByText('cut-1').first()).toBeVisible();
  await expect(page.getByText('Engaging').first()).toBeVisible();
  await expect(page.getByText('Pause').first()).toBeVisible();

  await page.locator('[data-testid="attention-point-2"]').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('2.0s');
});

const regressionReadoutPayload = {
  video_id: 'demo-video',
  duration_ms: 12000,
  scenes: [
    { scene_index: 0, start_ms: 0, end_ms: 3000, label: 'Hook', scene_id: 'scene-1', cut_id: 'cut-1' },
    {
      scene_index: 1,
      start_ms: 3000,
      end_ms: 6000,
      label: 'Build',
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main'
    },
    { scene_index: 2, start_ms: 6000, end_ms: 9000, label: 'Friction', scene_id: 'scene-3', cut_id: 'cut-3' },
    { scene_index: 3, start_ms: 9000, end_ms: 12000, label: 'Recovery', scene_id: 'scene-4', cut_id: 'cut-4' }
  ],
  cuts: [
    { cut_id: 'cut-1', start_ms: 0, end_ms: 1500, scene_id: 'scene-1' },
    { cut_id: 'cut-2', start_ms: 1500, end_ms: 3000, scene_id: 'scene-1' },
    { cut_id: 'cut-3', start_ms: 3000, end_ms: 4500, scene_id: 'scene-2' },
    { cut_id: 'cut-4', start_ms: 4500, end_ms: 6000, scene_id: 'scene-2', cta_id: 'cta-main' },
    { cut_id: 'cut-5', start_ms: 6000, end_ms: 7500, scene_id: 'scene-3' },
    { cut_id: 'cut-6', start_ms: 7500, end_ms: 9000, scene_id: 'scene-3' },
    { cut_id: 'cut-7', start_ms: 9000, end_ms: 10500, scene_id: 'scene-4' },
    { cut_id: 'cut-8', start_ms: 10500, end_ms: 12000, scene_id: 'scene-4' }
  ],
  cta_markers: [
    {
      cta_id: 'cta-main',
      video_time_ms: 4500,
      start_ms: 4200,
      end_ms: 5400,
      scene_id: 'scene-2',
      cut_id: 'cut-4',
      label: 'Main CTA'
    }
  ],
  traces: {
    attention_score: [
      { video_time_ms: 0, value: 66, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 74, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 78, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 63, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 66, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 58, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 40, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 34, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 38, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 70, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 83, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 90, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    attention_velocity: [
      { video_time_ms: 0, value: 0, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 8, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 4, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: -15, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 3, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: -8, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: -18, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: -6, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 4, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 32, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 13, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 7, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    blink_rate: [
      { video_time_ms: 0, value: 0.09, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.08, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.07, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 0.12, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 0.11, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 0.16, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 0.42, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 0.49, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 0.43, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 0.12, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 0.09, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 0.08, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    blink_inhibition: [
      { video_time_ms: 0, value: 0.34, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.38, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.4, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 0.2, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 0.24, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 0.12, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: -0.24, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: -0.31, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: -0.26, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 0.22, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 0.29, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 0.32, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    reward_proxy: [
      { video_time_ms: 0, value: 62, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 70, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 76, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 61, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 65, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 57, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 35, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 29, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 33, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 80, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 89, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 93, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    tracking_confidence: [
      { video_time_ms: 0, value: 0.85, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 1000, value: 0.87, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 2000, value: 0.88, scene_id: 'scene-1', cut_id: 'cut-1' },
      { video_time_ms: 3000, value: 0.78, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 4000, value: 0.79, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 5000, value: 0.74, scene_id: 'scene-2', cut_id: 'cut-2', cta_id: 'cta-main' },
      { video_time_ms: 6000, value: 0.42, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 7000, value: 0.35, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 8000, value: 0.4, scene_id: 'scene-3', cut_id: 'cut-3' },
      { video_time_ms: 9000, value: 0.8, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 10000, value: 0.86, scene_id: 'scene-4', cut_id: 'cut-4' },
      { video_time_ms: 11000, value: 0.88, scene_id: 'scene-4', cut_id: 'cut-4' }
    ],
    au_channels: [
      {
        au_name: 'AU04',
        points: [
          { video_time_ms: 0, value: 0.02 },
          { video_time_ms: 1000, value: 0.02 },
          { video_time_ms: 2000, value: 0.03 },
          { video_time_ms: 3000, value: 0.04 },
          { video_time_ms: 4000, value: 0.04 },
          { video_time_ms: 5000, value: 0.05 },
          { video_time_ms: 6000, value: 0.18 },
          { video_time_ms: 7000, value: 0.22 },
          { video_time_ms: 8000, value: 0.19 },
          { video_time_ms: 9000, value: 0.04 },
          { video_time_ms: 10000, value: 0.03 },
          { video_time_ms: 11000, value: 0.03 }
        ]
      },
      {
        au_name: 'AU06',
        points: [
          { video_time_ms: 0, value: 0.09 },
          { video_time_ms: 1000, value: 0.11 },
          { video_time_ms: 2000, value: 0.12 },
          { video_time_ms: 3000, value: 0.08 },
          { video_time_ms: 4000, value: 0.09 },
          { video_time_ms: 5000, value: 0.08 },
          { video_time_ms: 6000, value: 0.04 },
          { video_time_ms: 7000, value: 0.03 },
          { video_time_ms: 8000, value: 0.04 },
          { video_time_ms: 9000, value: 0.11 },
          { video_time_ms: 10000, value: 0.13 },
          { video_time_ms: 11000, value: 0.14 }
        ]
      },
      {
        au_name: 'AU12',
        points: [
          { video_time_ms: 0, value: 0.31 },
          { video_time_ms: 1000, value: 0.36 },
          { video_time_ms: 2000, value: 0.39 },
          { video_time_ms: 3000, value: 0.26 },
          { video_time_ms: 4000, value: 0.29 },
          { video_time_ms: 5000, value: 0.22 },
          { video_time_ms: 6000, value: 0.1 },
          { video_time_ms: 7000, value: 0.07 },
          { video_time_ms: 8000, value: 0.09 },
          { video_time_ms: 9000, value: 0.34 },
          { video_time_ms: 10000, value: 0.4 },
          { video_time_ms: 11000, value: 0.43 }
        ]
      }
    ]
  },
  segments: {
    attention_gain_segments: [
      {
        start_video_time_ms: 9000,
        end_video_time_ms: 11000,
        metric: 'attention_gain',
        magnitude: 16.8,
        confidence: 0.84,
        reason_codes: ['above_local_baseline', 'upward_velocity'],
        scene_id: 'scene-4'
      }
    ],
    attention_loss_segments: [
      {
        start_video_time_ms: 6000,
        end_video_time_ms: 8000,
        metric: 'attention_loss',
        magnitude: 15.4,
        confidence: 0.39,
        reason_codes: ['below_local_baseline', 'downward_velocity'],
        scene_id: 'scene-3'
      }
    ],
    golden_scenes: [
      {
        start_video_time_ms: 10000,
        end_video_time_ms: 11000,
        metric: 'golden_scene',
        magnitude: 89.0,
        confidence: 0.87,
        reason_codes: ['high_reward_proxy', 'high_attention_score'],
        scene_id: 'scene-4'
      }
    ],
    dead_zones: [
      {
        start_video_time_ms: 6000,
        end_video_time_ms: 8000,
        metric: 'dead_zone',
        magnitude: 17.3,
        confidence: 0.38,
        reason_codes: ['sustained_attention_drop', 'low_tracking_confidence'],
        scene_id: 'scene-3'
      }
    ],
    confusion_segments: [
      {
        start_video_time_ms: 6000,
        end_video_time_ms: 8000,
        metric: 'confusion_segment',
        magnitude: 3.1,
        confidence: 0.39,
        reason_codes: ['elevated_blink_rate', 'au4_friction_proxy'],
        scene_id: 'scene-3'
      }
    ]
  },
  diagnostics: [
    {
      card_type: 'golden_scene',
      scene_index: 3,
      scene_id: 'scene-4',
      cut_id: 'cut-4',
      cta_id: null,
      scene_label: 'Recovery',
      scene_thumbnail_url: null,
      start_video_time_ms: 10000,
      end_video_time_ms: 11000,
      primary_metric: 'reward_proxy',
      primary_metric_value: 89.0,
      why_flagged: 'Highest sustained reward proxy with strong late-scene retention.',
      confidence: 0.87,
      reason_codes: ['high_reward_proxy', 'attention_retention']
    },
    {
      card_type: 'hook_strength',
      scene_index: 0,
      scene_id: 'scene-1',
      cut_id: 'cut-1',
      cta_id: null,
      scene_label: 'Hook',
      scene_thumbnail_url: null,
      start_video_time_ms: 0,
      end_video_time_ms: 3000,
      primary_metric: 'hook_strength',
      primary_metric_value: 72.0,
      why_flagged: 'Opening window retained attention strongly.',
      confidence: 0.86,
      reason_codes: ['opening_window', 'positive_attention_retention']
    },
    {
      card_type: 'cta_receptivity',
      scene_index: 1,
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      scene_label: 'Build',
      scene_thumbnail_url: null,
      start_video_time_ms: 3000,
      end_video_time_ms: 5000,
      primary_metric: 'cta_receptivity',
      primary_metric_value: 63.5,
      why_flagged: 'CTA lead-in retained moderate attention before later drop.',
      confidence: 0.75,
      reason_codes: ['cta_lead_in_window', 'cta_on_window']
    },
    {
      card_type: 'attention_drop_scene',
      scene_index: 2,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      scene_label: 'Friction',
      scene_thumbnail_url: null,
      start_video_time_ms: 6000,
      end_video_time_ms: 8000,
      primary_metric: 'attention_drop_magnitude',
      primary_metric_value: 15.4,
      why_flagged: 'Largest sustained negative attention delta occurred here.',
      confidence: 0.39,
      reason_codes: ['below_local_baseline', 'downward_velocity']
    },
    {
      card_type: 'confusion_scene',
      scene_index: 2,
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      scene_label: 'Friction',
      scene_thumbnail_url: null,
      start_video_time_ms: 6000,
      end_video_time_ms: 8000,
      primary_metric: 'friction_score',
      primary_metric_value: 3.1,
      why_flagged: 'High AU4 plus elevated blink and falling attention indicates confusion.',
      confidence: 0.39,
      reason_codes: ['elevated_blink_rate', 'au4_friction_proxy']
    },
    {
      card_type: 'recovery_scene',
      scene_index: 3,
      scene_id: 'scene-4',
      cut_id: 'cut-4',
      cta_id: null,
      scene_label: 'Recovery',
      scene_thumbnail_url: null,
      start_video_time_ms: 9000,
      end_video_time_ms: 11000,
      primary_metric: 'attention_recovery_magnitude',
      primary_metric_value: 18.9,
      why_flagged: 'Attention recovered strongly after the mid-video drop.',
      confidence: 0.85,
      reason_codes: ['above_local_baseline', 'upward_velocity', 'post_drop_recovery']
    }
  ],
  quality_summary: {
    sessions_count: 2,
    participants_count: 2,
    total_trace_points: 24,
    face_ok_rate: 0.92,
    mean_brightness: 39.6,
    mean_tracking_confidence: 0.66,
    mean_quality_score: 0.64,
    low_confidence_windows: 3,
    usable_seconds: 8,
    quality_badge: 'medium',
    trace_source: 'mixed'
  },
  playback_telemetry: [
    {
      id: 'telemetry-r-1',
      session_id: 'session-regression-1',
      video_id: 'demo-video',
      event_type: 'pause',
      video_time_ms: 3100,
      wall_time_ms: 1700001003100,
      client_monotonic_ms: 3100,
      details: { mode: 'first_pass' },
      scene_id: 'scene-2',
      cut_id: 'cut-2',
      cta_id: 'cta-main',
      created_at: '2026-03-06T02:00:01Z'
    },
    {
      id: 'telemetry-r-2',
      session_id: 'session-regression-1',
      video_id: 'demo-video',
      event_type: 'seek_end',
      video_time_ms: 7600,
      wall_time_ms: 1700001007600,
      client_monotonic_ms: 7600,
      details: { fromVideoTimeMs: 8400, toVideoTimeMs: 7600 },
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      created_at: '2026-03-06T02:00:04Z'
    },
    {
      id: 'telemetry-r-3',
      session_id: 'session-regression-2',
      video_id: 'demo-video',
      event_type: 'abandonment',
      video_time_ms: 8200,
      wall_time_ms: 1700001008200,
      client_monotonic_ms: 8200,
      details: { reason: 'pagehide_before_completion', lastVideoTimeMs: 8200 },
      scene_id: 'scene-3',
      cut_id: 'cut-3',
      cta_id: null,
      created_at: '2026-03-06T02:00:05Z'
    }
  ],
  annotations: [],
  annotation_summary: {
    total_annotations: 0,
    engaging_moment_count: 0,
    confusing_moment_count: 0,
    stop_watching_moment_count: 0,
    cta_landed_moment_count: 0,
    marker_density: [],
    top_engaging_timestamps: [],
    top_confusing_timestamps: []
  },
  survey_summary: {
    responses_count: 0,
    overall_interest_mean: null,
    recall_comprehension_mean: null,
    desire_to_continue_or_take_action_mean: null,
    comment_count: 0
  },
  quality: {
    session_quality_summary: {
      sessions_count: 2,
      participants_count: 2,
      total_trace_points: 24,
      face_ok_rate: 0.92,
      mean_brightness: 39.6,
      mean_tracking_confidence: 0.66,
      mean_quality_score: 0.64,
      low_confidence_windows: 3,
      usable_seconds: 8,
      quality_badge: 'medium',
      trace_source: 'mixed'
    },
    low_confidence_windows: [
      {
        start_video_time_ms: 6000,
        end_video_time_ms: 9000,
        mean_tracking_confidence: 0.39,
        quality_flags: ['low_light', 'blur', 'high_yaw_pitch']
      }
    ]
  }
};

const regressionReadoutPayloadCanonical = {
  ...regressionReadoutPayload,
  schema_version: '1.0.0',
  aggregate: true,
  variant_id: 'variant-regression',
  session_id: null,
  timebase: {
    window_ms: 1000,
    step_ms: 1000
  },
  context: {
    scenes: regressionReadoutPayload.scenes,
    cuts: regressionReadoutPayload.cuts,
    cta_markers: regressionReadoutPayload.cta_markers
  },
  traces: {
    ...regressionReadoutPayload.traces,
    attention_score: regressionReadoutPayload.traces.attention_score.map((point) => ({
      ...point,
      median: point.value,
      ci_low:
        point.value !== null && point.value !== undefined
          ? Number(Math.max(0, point.value - 6).toFixed(6))
          : null,
      ci_high:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, point.value + 6).toFixed(6))
          : null
    })),
    reward_proxy: regressionReadoutPayload.traces.reward_proxy.map((point) => ({
      ...point,
      median: point.value,
      ci_low:
        point.value !== null && point.value !== undefined
          ? Number(Math.max(0, point.value - 7).toFixed(6))
          : null,
      ci_high:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, point.value + 7).toFixed(6))
          : null
    })),
    valence_proxy: regressionReadoutPayload.traces.reward_proxy.map((point) => ({
      ...point,
      value: point.value !== null && point.value !== undefined ? Number((point.value * 0.9).toFixed(6)) : null
    })),
    arousal_proxy: regressionReadoutPayload.traces.attention_score.map((point, index) => ({
      ...point,
      value:
        point.value !== null && point.value !== undefined
          ? Number(
              Math.min(
                100,
                Math.max(
                  0,
                  point.value * 0.72 + Math.abs(regressionReadoutPayload.traces.attention_velocity[index]?.value ?? 0) * 1.3
                )
              ).toFixed(6)
            )
          : null
    })),
    novelty_proxy: regressionReadoutPayload.traces.attention_velocity.map((point) => ({
      ...point,
      value:
        point.value !== null && point.value !== undefined
          ? Number(Math.min(100, Math.max(0, 20 + Math.abs(point.value) * 6.8)).toFixed(6))
          : null
    }))
  },
  labels: {
    annotations: regressionReadoutPayload.annotations,
    annotation_summary: regressionReadoutPayload.annotation_summary,
    survey_summary: regressionReadoutPayload.survey_summary
  },
  aggregate_metrics: {
    attention_synchrony: 0.71,
    blink_synchrony: 0.58,
    grip_control_score: 0.645,
    ci_method: 'sem_95',
    included_sessions: 2,
    downweighted_sessions: 1
  }
};

test.beforeEach(async ({ page }) => {
  await page.route('**/videos/demo-video/readout*', async (route) => {
    if (route.request().url().includes('/readout/export-package')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(readoutPayload)
    });
  });
});

test('home catalog lists recordings and opens latest-session deep dive', async ({ page }) => {
  await page.route('**/videos?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            video_id: 'demo-video',
            study_id: 'study-1',
            study_name: 'Readout Study',
            title: 'Demo Stimulus',
            source_url: 'https://cdn.example.com/demo.mp4',
            duration_ms: 9000,
            created_at: '2026-03-06T01:00:00Z',
            sessions_count: 3,
            completed_sessions_count: 2,
            participants_count: 3,
            last_session_id: 'session-latest',
            last_session_at: '2026-03-06T01:30:00Z',
            last_session_status: 'completed',
            latest_trace_at: '2026-03-06T01:31:00Z',
            recent_sessions: [
              {
                id: 'session-latest',
                participant_id: 'participant-1',
                status: 'completed',
                created_at: '2026-03-06T01:30:00Z'
              }
            ]
          }
        ]
      })
    });
  });

  await page.goto('/');
  await expect(page.getByTestId('catalog-recording-card')).toHaveCount(1);
  await expect(page.getByText('Demo Stimulus')).toBeVisible();
  await expect(page.getByText('Sessions 3')).toBeVisible();

  await page.getByTestId('catalog-open-latest-session').click();
  await expect(page).toHaveURL(/\/videos\/demo-video\?aggregate=false&session_id=session-latest/);
  await expect(page.getByTestId('session-id-filter')).toHaveValue('session-latest');
  await expect(page.getByTestId('aggregate-switch')).not.toBeChecked();
});

test('home input defaults to timeline report route', async ({ page }) => {
  await page.route('**/videos?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });

  await page.goto('/');
  await page.getByTestId('video-id-input').fill('demo-video');
  await page.getByTestId('open-video-button').click();
  await expect(page).toHaveURL(/\/videos\/demo-video\/timeline-report/);
  await expect(page.getByTestId('timeline-report-title')).toContainText('Scene-by-Scene Timeline Report');
});

test('observability page loads and renders latest snapshot summary', async ({ page }) => {
  await page.route('**/videos?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });

  await page.route('**/observability/neuro', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'alert',
        enabled: true,
        history_enabled: true,
        history_entry_count: 2,
        history_max_entries: 500,
        drift_alert_threshold: 12.0,
        recent_window: 25,
        recent_snapshot_count: 2,
        recent_drift_alert_count: 1,
        recent_drift_alert_rate: 0.5,
        mean_missing_signal_rate: 0.3,
        mean_fallback_rate: 0.2,
        mean_confidence: 0.68,
        latest_snapshot: {
          recorded_at: '2026-03-08T01:10:00Z',
          video_id: 'demo-video',
          variant_id: 'variant-a',
          model_signature: 'neuro_taxonomy_v2',
          drift_status: 'alert',
          missing_signal_rate: 0.4,
          fallback_rate: 0.3,
          confidence_mean: 0.64,
          metrics_exceeding_threshold: ['arrest_score', 'cta_reception_score']
        },
        warnings: ['recent_drift_alerts_present']
      })
    });
  });
  await page.route('**/observability/capture-archives', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        enabled: true,
        purge_enabled: true,
        retention_days: 30,
        purge_batch_size: 500,
        encryption_mode: 'none',
        ingestion_event_count: 4,
        success_count: 4,
        failure_count: 0,
        failure_rate: 0,
        recent_window_hours: 24,
        recent_success_count: 2,
        recent_failure_count: 0,
        recent_failure_rate: 0,
        total_archives: 2,
        total_frames: 180,
        total_frame_pointers: 0,
        total_uncompressed_bytes: 10000,
        total_compressed_bytes: 3500,
        oldest_archive_at: '2026-03-08T00:10:00Z',
        newest_archive_at: '2026-03-08T01:10:00Z',
        top_failure_codes: [],
        warnings: []
      })
    });
  });

  await page.goto('/');
  await page.getByTestId('open-observability-button').click();
  await expect(page).toHaveURL(/\/observability/);
  await expect(page.getByTestId('observability-title')).toContainText('Neuro Score Observability');
  await expect(page.getByTestId('observability-status-chip')).toContainText('Status alert');
  await expect(page.getByTestId('observability-warning')).toContainText('recent_drift_alerts_present');
  await expect(page.getByTestId('observability-latest-drift-alert')).toContainText('arrest_score');
});

test('header observability link routes to observability page', async ({ page }) => {
  await page.route('**/videos?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });

  await page.route('**/observability/neuro', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        enabled: true,
        history_enabled: false,
        history_entry_count: 0,
        history_max_entries: 500,
        drift_alert_threshold: 12.0,
        recent_window: 25,
        recent_snapshot_count: 0,
        recent_drift_alert_count: 0,
        recent_drift_alert_rate: null,
        mean_missing_signal_rate: null,
        mean_fallback_rate: null,
        mean_confidence: null,
        latest_snapshot: null,
        warnings: ['history_path_not_configured']
      })
    });
  });
  await page.route('**/observability/capture-archives', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'no_data',
        enabled: true,
        purge_enabled: true,
        retention_days: 30,
        purge_batch_size: 500,
        encryption_mode: 'none',
        ingestion_event_count: 0,
        success_count: 0,
        failure_count: 0,
        failure_rate: null,
        recent_window_hours: 24,
        recent_success_count: 0,
        recent_failure_count: 0,
        recent_failure_rate: null,
        total_archives: 0,
        total_frames: 0,
        total_frame_pointers: 0,
        total_uncompressed_bytes: 0,
        total_compressed_bytes: 0,
        oldest_archive_at: null,
        newest_archive_at: null,
        top_failure_codes: [],
        warnings: ['capture_ingest_history_empty']
      })
    });
  });

  await page.goto('/');
  await page.getByTestId('header-observability-link').click();
  await expect(page).toHaveURL(/\/observability/);
  await expect(page.getByTestId('observability-title')).toContainText('Neuro Score Observability');
});

test('syncs player timeline when chart point is clicked and shows hover values', async ({ page }) => {
  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('page-title')).toContainText('Readout Dashboard');
  await expect(page.getByTestId('legacy-view-callout')).toContainText('legacy deep-dive surface');
  const neuroSnapshotCardCount = await page.getByTestId('neuro-snapshot-card').count();
  if (neuroSnapshotCardCount > 0) {
    await expect(page.getByTestId('neuro-snapshot-arrest-chip')).toContainText('Arrest');
    await expect(page.getByTestId('neuro-snapshot-lift-chip')).toContainText('Synthetic Lift Prior');
  } else {
    await expect(page.getByTestId('neuro-snapshot-missing-alert')).toBeVisible();
  }
  await expect(page.getByTestId('grip-control-card')).toBeVisible();
  await expect(page.getByTestId('attention-synchrony-chip')).toContainText('0.820');
  await expect(page.getByTestId('blink-synchrony-chip')).toContainText('0.760');
  await expect(page.getByTestId('grip-score-chip')).toContainText('0.790');
  await expect(page.getByTestId('attentional-synchrony-card')).toBeVisible();
  await expect(page.getByTestId('attentional-synchrony-pathway-chip')).toContainText('Direct panel gaze');
  await expect(page.getByTestId('attentional-synchrony-global-chip')).toContainText('81.6');
  await expect(page.getByTestId('attentional-synchrony-confidence-chip')).toContainText('88%');
  await expect(page.getByTestId('attentional-synchrony-evidence-summary')).toContainText(
    'primary pathway'
  );
  await expect(page.getByTestId('narrative-control-card')).toBeVisible();
  await expect(page.getByTestId('narrative-control-pathway-chip')).toContainText('Timeline grammar');
  await expect(page.getByTestId('narrative-control-global-chip')).toContainText('73.8');
  await expect(page.getByTestId('narrative-control-confidence-chip')).toContainText('79%');
  await expect(page.getByTestId('narrative-control-evidence-summary')).toContainText(
    'coherent payoff reveal'
  );
  await expect(page.getByTestId('reward-anticipation-card')).toBeVisible();
  await expect(page.getByTestId('reward-anticipation-pathway-chip')).toContainText('Timeline dynamics');
  await expect(page.getByTestId('reward-anticipation-global-chip')).toContainText('76.4');
  await expect(page.getByTestId('reward-anticipation-confidence-chip')).toContainText('82%');
  await expect(page.getByTestId('reward-anticipation-evidence-summary')).toContainText(
    'late-resolution timing warning'
  );
  await page.getByTestId('narrative-control-scene-jump-0').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('0.0s');
  await page.getByTestId('reward-anticipation-ramp-jump-0').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('2.0s');
  await expect(page.getByTestId('quality-badge')).toContainText('Quality medium');
  await expect(page.getByTestId('trace-source-badge')).toContainText('Provided traces');
  await expect(page.getByTestId('usable-seconds-chip')).toContainText('Usable seconds 6.0');
  await expect(page.getByTestId('low-confidence-window')).toHaveCount(1);
  await expect(page.getByTestId('ci-band-note')).toBeVisible();
  await page.getByTestId('attentional-synchrony-segment-jump-0').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('0.0s');
  await page.locator('[data-testid="attention-point-2"]').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('2.0s');

  await page.locator('[data-testid="attention-point-2"]').hover();
  await expect(page.getByTestId('trace-hover-tooltip')).toContainText('attention_score');
  await expect(page.getByTestId('trace-hover-tooltip')).toContainText('reward_proxy');
  await page.locator('[data-testid="attention-point-4"]').hover();
  await expect(page.getByTestId('trace-hover-tooltip')).toContainText('cta: cta-main');
});

test('supports trace layer toggles', async ({ page }) => {
  await page.goto('/videos/demo-video');
  await page.getByTestId('trace-layers-summary').click();
  await expect(page.getByTestId('toggle-attention-velocity')).toBeChecked();
  await page.getByTestId('toggle-attention-velocity').click();
  await expect(page.getByTestId('toggle-attention-velocity')).not.toBeChecked();

  await expect(page.getByTestId('toggle-au-AU12')).toBeChecked();
  await page.getByTestId('toggle-au-AU12').click();
  await expect(page.getByTestId('toggle-au-AU12')).not.toBeChecked();
});

test('segment cards jump to matching timeline location', async ({ page }) => {
  await page.goto('/videos/demo-video');

  await page.getByTestId('segment-jump-attention-gains-card-0').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('1.0s');
});

test('diagnostic cards render and jump to scene windows', async ({ page }) => {
  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('diagnostic-card-golden_scene')).toContainText('Golden Scene');
  await expect(page.getByTestId('diagnostic-card-cta_receptivity')).toContainText('CTA Receptivity');

  await page.getByTestId('diagnostic-jump-attention_drop_scene').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('3.0s');
});

test('clicking empty chart space still seeks video', async ({ page }) => {
  await page.goto('/videos/demo-video');

  const chart = page.getByTestId('summary-chart');
  const box = await chart.boundingBox();
  if (!box) {
    throw new Error('summary chart did not render');
  }

  await chart.click({
    position: {
      x: Math.round(box.width * 0.75),
      y: Math.round(box.height * 0.22)
    }
  });

  await expect
    .poll(async () => {
      const text = await page.getByTestId('current-time-chip').innerText();
      const match = text.match(/Current:\s*([0-9.]+)s/);
      return match ? Number(match[1]) : 0;
    })
    .toBeGreaterThan(2);
});

test('renders explicit label overlays and survey summary', async ({ page }) => {
  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('marker-count-engaging_moment')).toContainText('Engaging 2');
  await expect(page.getByTestId('marker-count-confusing_moment')).toContainText('Confusing 1');
  await expect(page.getByTestId('marker-density-note')).toBeVisible();
  await expect(page.getByTestId('labels-survey-summary-card')).toContainText('Overall interest: 3.00');
  await expect(page.getByTestId('labels-survey-summary-card')).toContainText(
    'Comprehension / recall: 3.50'
  );
  await expect(page.getByTestId('labels-survey-summary-card')).toContainText(
    'Keep watching / take action: 4.00'
  );
  await expect(page.getByTestId('labels-survey-summary-card')).toContainText('Responses: 8');

  await page.getByTestId('top-engaging-jump-0').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('4.0s');
});

test('renders playback telemetry summary including pause, seek, and abandonment', async ({ page }) => {
  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('playback-telemetry-card')).toBeVisible();
  await expect(page.getByTestId('telemetry-count-pause')).toContainText('Pause 1');
  await expect(page.getByTestId('telemetry-count-seek')).toContainText('Seek 1');
  await expect(page.getByTestId('telemetry-count-abandonment')).toContainText('Abandonment 1');
  await expect(page.getByTestId('abandonment-point-card')).toContainText('7.3s');
});

test('applies session, variant, and aggregate filters for readout overlays', async ({ page }) => {
  const requestUrls: string[] = [];
  await page.route('**/videos/demo-video/readout*', async (route) => {
    requestUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(readoutPayload)
    });
  });

  await page.goto('/videos/demo-video');
  await page.getByTestId('aggregate-switch').click();
  await page.getByTestId('session-id-filter').fill('session-a');
  await page.getByTestId('variant-id-filter').fill('variant-a');
  await page.getByTestId('apply-filter-button').click();

  await expect
    .poll(() => {
      const lastUrl = requestUrls[requestUrls.length - 1];
      if (!lastUrl) {
        return '';
      }
      const query = new URL(lastUrl).searchParams;
      const session = query.get('session_id') ?? query.get('sessionId');
      const variant = query.get('variant_id') ?? query.get('variantId');
      return `${query.get('aggregate')}|${session}|${variant}`;
    })
    .toBe('false|session-a|variant-a');
});

test('exports readout package via dedicated endpoint', async ({ page }) => {
  const requestUrls: string[] = [];
  await page.route('**/videos/demo-video/readout/export-package*', async (route) => {
    requestUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(exportPackagePayload)
    });
  });

  await page.goto('/videos/demo-video');
  await page.getByTestId('export-package-button').click();

  await expect
    .poll(() => {
      const url = requestUrls[requestUrls.length - 1];
      if (!url) {
        return '';
      }
      const query = new URL(url).searchParams;
      const windowMs = query.get('window_ms') ?? query.get('windowMs');
      return `${query.get('aggregate')}|${windowMs}`;
    })
    .toBe('true|1000');
});

test('regression: 4-scene readout renders boundaries, CTA, confidence warning, and session/aggregate flow', async ({
  page
}) => {
  const requestUrls: string[] = [];
  await page.route('**/videos/demo-video/readout*', async (route) => {
    if (route.request().url().includes('/readout/export-package')) {
      await route.fallback();
      return;
    }
    requestUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(regressionReadoutPayloadCanonical)
    });
  });

  await page.goto('/videos/demo-video');

  const chart = page.getByTestId('summary-chart');
  await expect(chart.getByText('Hook', { exact: true }).first()).toBeVisible();
  await expect(chart.getByText('Build', { exact: true }).first()).toBeVisible();
  await expect(chart.getByText('Friction', { exact: true }).first()).toBeVisible();
  await expect(chart.getByText('Recovery', { exact: true }).first()).toBeVisible();
  await page.locator('[data-testid="attention-point-4"]').hover();
  await expect(page.getByTestId('trace-hover-tooltip')).toContainText('cta: cta-main');
  await expect(page.getByTestId('quality-warning')).toBeVisible();
  await expect(page.getByTestId('quality-badge')).toContainText('Quality medium');
  await expect(page.getByTestId('usable-seconds-chip')).toContainText('Usable seconds 8.0');
  await expect(page.getByTestId('low-confidence-window')).toHaveCount(1);
  await expect(page.getByTestId('grip-control-card')).toBeVisible();
  await expect(page.getByTestId('grip-score-chip')).toContainText('0.645');

  await expect(page.getByTestId('attention-losses-card')).toContainText('6.0s - 8.0s');
  await expect(page.getByTestId('golden-scenes-card')).toContainText('10.0s - 11.0s');

  await page.locator('[data-testid="attention-point-10"]').click();
  await expect(page.getByTestId('current-time-chip')).toContainText('10.0s');

  await page.locator('[data-testid="attention-point-10"]').hover();
  await expect(page.getByTestId('trace-hover-tooltip')).toContainText('reward_proxy');
  await expect(page.getByTestId('trace-hover-tooltip')).not.toContainText('dopamine');

  await page.getByTestId('aggregate-switch').click();
  await page.getByTestId('session-id-filter').fill('session-regression-1');
  await page.getByTestId('variant-id-filter').fill('variant-regression');
  await page.getByTestId('apply-filter-button').click();

  await expect
    .poll(() => {
      const initialUrl = requestUrls[0];
      const lastUrl = requestUrls[requestUrls.length - 1];
      if (!initialUrl || !lastUrl) {
        return '';
      }
      const first = new URL(initialUrl).searchParams;
      const final = new URL(lastUrl).searchParams;
      const session = final.get('session_id') ?? final.get('sessionId');
      const variant = final.get('variant_id') ?? final.get('variantId');
      return `${first.get('aggregate')}|${final.get('aggregate')}|${session}|${variant}`;
    })
    .toBe('true|false|session-regression-1|variant-regression');
});

test('timeline-report route renders scene-by-scene tracks, key moments, and evidence windows', async ({
  page
}) => {
  await page.route('**/videos/demo-video/readout*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(timelineReportReadoutPayload)
    });
  });

  await page.goto('/videos/demo-video/timeline-report');

  await expect(page.getByTestId('timeline-report-title')).toContainText('Scene-by-Scene Timeline Report');
  await expect(page.getByTestId('timeline-track-toggle-attention_arrest')).toBeVisible();
  await expect(page.getByTestId('timeline-track-toggle-attentional_synchrony')).toBeVisible();
  await expect(page.getByTestId('timeline-track-toggle-narrative_control')).toBeVisible();
  await expect(page.getByTestId('timeline-key-moments-lane')).toBeVisible();

  await expect(page.locator('[data-testid^="timeline-track-row-"]')).toHaveCount(8);
  await expect(page.locator('[data-testid^="timeline-key-moment-hook_window-"]')).toHaveCount(1);
  await expect(page.locator('[data-testid^="timeline-key-moment-cta_window-"]')).toHaveCount(1);
  await expect
    .poll(async () => page.locator('[data-testid^="timeline-track-window-"]').count())
    .toBeGreaterThanOrEqual(3);

  await expect(page.getByTestId('timeline-track-row-attention_arrest')).toBeVisible();
  await expect(page.getByTestId('timeline-track-row-reward_anticipation')).toBeVisible();
  await expect(page.getByTestId('timeline-track-row-cta_reception')).toBeVisible();

  await page.getByTestId('timeline-track-toggle-au_friction').click();
  await expect(page.getByTestId('timeline-track-row-au_friction')).toHaveCount(0);

  await page.screenshot({ path: 'test-results/timeline-report-demo.png', fullPage: true });
});

test('renders creator rollup layer with reception warnings and organic prior labels', async ({
  page
}) => {
  await page.unroute('**/videos/demo-video/readout*');
  await page.route('**/videos/demo-video/readout*', async (route) => {
    if (route.request().url().includes('/readout/export-package')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(readoutPayloadCreatorMode)
    });
  });

  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('product-rollup-creator-card')).toBeVisible();
  await expect(page.getByTestId('creator-reception-score-chip')).toContainText('Reception Score');
  await expect(page.getByTestId('creator-organic-reach-chip')).toContainText('Organic Reach Prior');
  await expect(page.getByTestId('creator-warning-weak_hook')).toBeVisible();
});

test('renders enterprise rollup layer with lift distinction and decision-support summaries', async ({
  page
}) => {
  await page.unroute('**/videos/demo-video/readout*');
  await page.route('**/videos/demo-video/readout*', async (route) => {
    if (route.request().url().includes('/readout/export-package')) {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(readoutPayloadEnterpriseMode)
    });
  });

  await page.goto('/videos/demo-video');

  await expect(page.getByTestId('product-rollup-enterprise-card')).toBeVisible();
  await expect(page.getByTestId('enterprise-paid-lift-chip')).toContainText('Paid Lift Prior');
  await expect(page.getByTestId('enterprise-brand-memory-chip')).toContainText('Brand Memory Prior');
  await expect(page.getByTestId('enterprise-cta-reception-chip')).toContainText('CTA Reception Score');
  await expect(page.getByTestId('enterprise-lift-distinction-note')).toContainText('Measured status');
  await expect(page.getByTestId('enterprise-media-summary')).toBeVisible();
  await expect(page.getByTestId('enterprise-creative-summary')).toBeVisible();
});

test('predictor page submits a video URL and renders predicted reaction layers', async ({ page }) => {
  await page.route('**/predict', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        model_artifact: 'artifacts/baseline_xgb.joblib',
        predictions: [
          { t_sec: 0, reward_proxy: 51, attention: 51, blink_inhibition: 0.21, dial: 52 },
          { t_sec: 1, reward_proxy: 59, attention: 59, blink_inhibition: 0.18, dial: 57 },
          { t_sec: 2, reward_proxy: 65, attention: 65, blink_inhibition: 0.1, dial: 63 },
          { t_sec: 3, reward_proxy: 54, attention: 54, blink_inhibition: -0.05, dial: 48 }
        ]
      })
    });
  });

  await page.goto('/predictor');
  await page.getByTestId('predictor-video-url-input').fill('https://cdn.example.com/trailer.mp4');
  await page.getByTestId('predictor-submit').click();

  await expect(page.getByText('Prediction output')).toBeVisible();
  await expect(page.getByTestId('predictor-video-player')).toBeVisible();
  await expect(page.getByTestId('predictor-chart')).toBeVisible();
  await expect(page.getByText('attention_score', { exact: true })).toBeVisible();
  await expect(page.getByText('reward_proxy', { exact: true })).toBeVisible();
  await expect(page.getByText('novelty_proxy', { exact: true })).toBeVisible();
  await page.getByTestId('predictor-event-reward-0-2').click();
  await expect(page.getByTestId('predictor-current-time')).toContainText('2.0s');
});
