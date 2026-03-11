import { z } from 'zod';

export const readoutSchemaVersion = '1.0.0';

const annotationMarkerTypeSchema = z.enum([
  'engaging_moment',
  'confusing_moment',
  'stop_watching_moment',
  'cta_landed_moment'
]);

const readoutSceneSchema = z.object({
  scene_index: z.number().int().nonnegative(),
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().nonnegative(),
  label: z.string().nullable().optional(),
  thumbnail_url: z.string().nullable().optional(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional()
});

const readoutCutSchema = z.object({
  cut_id: z.string().min(1),
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().nonnegative(),
  scene_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional(),
  label: z.string().nullable().optional()
});

const readoutCtaMarkerSchema = z.object({
  cta_id: z.string().min(1),
  video_time_ms: z.number().int().nonnegative(),
  start_ms: z.number().int().nonnegative().nullable().optional(),
  end_ms: z.number().int().nonnegative().nullable().optional(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  label: z.string().nullable().optional()
});

const readoutTracePointSchema = z.object({
  video_time_ms: z.number().int().nonnegative(),
  value: z.number().nullable(),
  median: z.number().nullable().optional(),
  ci_low: z.number().nullable().optional(),
  ci_high: z.number().nullable().optional(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional()
});

const readoutAuChannelSchema = z.object({
  au_name: z.string().min(1),
  points: z.array(readoutTracePointSchema)
});

const readoutSegmentSchema = z.object({
  start_video_time_ms: z.number().int().nonnegative(),
  end_video_time_ms: z.number().int().nonnegative(),
  metric: z.string().min(1),
  magnitude: z.number(),
  confidence: z.number().nullable().optional(),
  reason_codes: z.array(z.string()),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional(),
  distance_to_cta_ms: z.number().int().nullable().optional(),
  cta_window: z.enum(['pre_cta', 'on_cta', 'post_cta']).nullable().optional(),
  score: z.number().nullable().optional(),
  notes: z.string().nullable().optional()
});

const diagnosticCardSchema = z.object({
  card_type: z.enum([
    'golden_scene',
    'hook_strength',
    'cta_receptivity',
    'attention_drop_scene',
    'confusion_scene',
    'recovery_scene'
  ]),
  scene_index: z.number().int().nullable().optional(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional(),
  scene_label: z.string().nullable().optional(),
  scene_thumbnail_url: z.string().nullable().optional(),
  start_video_time_ms: z.number().int().nonnegative(),
  end_video_time_ms: z.number().int().nonnegative(),
  primary_metric: z.string().min(1),
  primary_metric_value: z.number(),
  why_flagged: z.string(),
  confidence: z.number().nullable().optional(),
  reason_codes: z.array(z.string())
});

const markerDensityPointSchema = z.object({
  marker_type: annotationMarkerTypeSchema,
  video_time_ms: z.number().int().nonnegative(),
  count: z.number().int().positive(),
  density: z.number().nonnegative(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional()
});

const markerTimestampSummarySchema = z.object({
  video_time_ms: z.number().int().nonnegative(),
  count: z.number().int().positive(),
  density: z.number().nonnegative(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional()
});

const annotationSummarySchema = z.object({
  total_annotations: z.number().int().nonnegative(),
  engaging_moment_count: z.number().int().nonnegative(),
  confusing_moment_count: z.number().int().nonnegative(),
  stop_watching_moment_count: z.number().int().nonnegative(),
  cta_landed_moment_count: z.number().int().nonnegative(),
  marker_density: z.array(markerDensityPointSchema),
  top_engaging_timestamps: z.array(markerTimestampSummarySchema),
  top_confusing_timestamps: z.array(markerTimestampSummarySchema)
});

const surveySummarySchema = z.object({
  responses_count: z.number().int().nonnegative(),
  overall_interest_mean: z.number().nullable().optional(),
  recall_comprehension_mean: z.number().nullable().optional(),
  desire_to_continue_or_take_action_mean: z.number().nullable().optional(),
  comment_count: z.number().int().nonnegative()
});

const annotationSchema = z.object({
  id: z.string().min(1),
  session_id: z.string().min(1),
  video_id: z.string().min(1),
  marker_type: annotationMarkerTypeSchema,
  video_time_ms: z.number().int().nonnegative(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional(),
  note: z.string().nullable(),
  created_at: z.string()
});

const playbackTelemetryEventSchema = z.object({
  id: z.string().min(1),
  session_id: z.string().min(1),
  video_id: z.string().min(1),
  event_type: z.string().min(1),
  video_time_ms: z.number().int().nonnegative(),
  wall_time_ms: z.number().int().nonnegative().nullable().optional(),
  client_monotonic_ms: z.number().int().nonnegative().nullable().optional(),
  details: z.record(z.string(), z.unknown()).nullable().optional(),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional(),
  created_at: z.string()
});

const readoutQualitySummarySchema = z.object({
  sessions_count: z.number().int().nonnegative(),
  participants_count: z.number().int().nonnegative(),
  total_trace_points: z.number().int().nonnegative(),
  face_ok_rate: z.number(),
  mean_brightness: z.number(),
  mean_tracking_confidence: z.number().nullable().optional(),
  mean_quality_score: z.number().nullable().optional(),
  low_confidence_windows: z.number().int().nonnegative(),
  usable_seconds: z.number().nullable().optional(),
  quality_badge: z.enum(['high', 'medium', 'low']).nullable().optional(),
  trace_source: z.enum(['provided', 'synthetic_fallback', 'mixed', 'unknown']).nullable().optional()
});

const readoutLowConfidenceWindowSchema = z.object({
  start_video_time_ms: z.number().int().nonnegative(),
  end_video_time_ms: z.number().int().nonnegative(),
  mean_tracking_confidence: z.number().nullable().optional(),
  quality_flags: z.array(z.string()).optional().default([])
});

const attentionalSynchronyPathwaySchema = z.enum([
  'direct_panel_gaze',
  'fallback_proxy',
  'insufficient_data'
]);

const attentionalSynchronyTimelineScoreSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  pathway: attentionalSynchronyPathwaySchema,
  reason: z.string().min(1)
});

const attentionalSynchronyExtremaSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  score: z.number().min(0).max(100),
  reason: z.string().min(1)
});

const attentionalSynchronyDiagnosticsSchema = z.object({
  pathway: attentionalSynchronyPathwaySchema,
  global_score: z.number().min(0).max(100).nullable().optional(),
  confidence: z.number().min(0).max(1).nullable().optional(),
  segment_scores: z.array(attentionalSynchronyTimelineScoreSchema).default([]),
  peaks: z.array(attentionalSynchronyExtremaSchema).default([]),
  valleys: z.array(attentionalSynchronyExtremaSchema).default([]),
  evidence_summary: z.string().min(1),
  signals_used: z.array(z.string().min(1)).default([])
});

const narrativeControlPathwaySchema = z.enum([
  'timeline_grammar',
  'fallback_proxy',
  'insufficient_data'
]);

const narrativeControlSceneScoreSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  scene_id: z.string().nullable().optional(),
  scene_label: z.string().nullable().optional(),
  fragmentation_index: z.number().min(0).max(1).nullable().optional(),
  boundary_density: z.number().min(0).nullable().optional(),
  motion_continuity: z.number().min(0).max(1).nullable().optional(),
  ordering_pattern: z.enum(['context_before_face', 'face_before_context', 'balanced']).nullable().optional(),
  summary: z.string().min(1)
});

const narrativeControlMomentContributionSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  contribution: z.number(),
  category: z.string().min(1),
  reason: z.string().min(1),
  scene_id: z.string().nullable().optional(),
  cut_id: z.string().nullable().optional(),
  cta_id: z.string().nullable().optional()
});

const narrativeControlHeuristicCheckSchema = z.object({
  heuristic_key: z.string().min(1),
  passed: z.boolean(),
  score_delta: z.number(),
  reason: z.string().min(1),
  start_ms: z.number().int().nonnegative().nullable().optional(),
  end_ms: z.number().int().positive().nullable().optional()
});

const narrativeControlDiagnosticsSchema = z.object({
  pathway: narrativeControlPathwaySchema,
  global_score: z.number().min(0).max(100).nullable().optional(),
  confidence: z.number().min(0).max(1).nullable().optional(),
  scene_scores: z.array(narrativeControlSceneScoreSchema).default([]),
  disruption_penalties: z.array(narrativeControlMomentContributionSchema).default([]),
  reveal_structure_bonuses: z.array(narrativeControlMomentContributionSchema).default([]),
  top_contributing_moments: z.array(narrativeControlMomentContributionSchema).default([]),
  heuristic_checks: z.array(narrativeControlHeuristicCheckSchema).default([]),
  evidence_summary: z.string().min(1),
  signals_used: z.array(z.string().min(1)).default([])
});

const rewardAnticipationPathwaySchema = z.enum([
  'timeline_dynamics',
  'fallback_proxy',
  'insufficient_data'
]);

const rewardAnticipationTimelineWindowTypeSchema = z.enum([
  'anticipation_ramp',
  'payoff_window'
]);

const rewardAnticipationTimelineWindowSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  window_type: rewardAnticipationTimelineWindowTypeSchema,
  reason: z.string().min(1),
  ramp_slope: z.number().nullable().optional(),
  reward_delta: z.number().nullable().optional(),
  tension_level: z.number().min(0).max(1).nullable().optional(),
  release_level: z.number().min(0).max(1).nullable().optional()
});

const rewardAnticipationWarningSeveritySchema = z.enum(['low', 'medium', 'high']);

const rewardAnticipationWarningSchema = z.object({
  warning_key: z.string().min(1).max(128),
  severity: rewardAnticipationWarningSeveritySchema,
  message: z.string().min(1),
  start_ms: z.number().int().nonnegative().nullable().optional(),
  end_ms: z.number().int().positive().nullable().optional(),
  metric_value: z.number().nullable().optional()
});

const rewardAnticipationDiagnosticsSchema = z.object({
  pathway: rewardAnticipationPathwaySchema,
  global_score: z.number().min(0).max(100).nullable().optional(),
  confidence: z.number().min(0).max(1).nullable().optional(),
  anticipation_ramps: z.array(rewardAnticipationTimelineWindowSchema).default([]),
  payoff_windows: z.array(rewardAnticipationTimelineWindowSchema).default([]),
  warnings: z.array(rewardAnticipationWarningSchema).default([]),
  anticipation_strength: z.number().min(0).max(1).nullable().optional(),
  payoff_release_strength: z.number().min(0).max(1).nullable().optional(),
  tension_release_balance: z.number().min(0).max(1).nullable().optional(),
  evidence_summary: z.string().min(1),
  signals_used: z.array(z.string().min(1)).default([])
});

const syntheticLiftPriorPathwaySchema = z.enum([
  'taxonomy_regression',
  'fallback_proxy',
  'insufficient_data'
]);

const syntheticLiftCalibrationStatusSchema = z.enum([
  'uncalibrated',
  'provisional',
  'geox_calibrated',
  'truth_layer_unavailable'
]);

const syntheticLiftPriorFeatureInputSchema = z.object({
  feature_name: z.string().min(1).max(128),
  source: z.enum(['taxonomy', 'legacy_performance', 'calibration']),
  raw_value: z.number(),
  normalized_value: z.number().min(0).max(1),
  weight: z.number().min(0)
});

const syntheticLiftPriorTimelineWindowSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().positive(),
  score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  reason: z.string().min(1),
  contribution: z.number().nullable().optional()
});

const syntheticLiftPriorDiagnosticsSchema = z.object({
  pathway: syntheticLiftPriorPathwaySchema,
  global_score: z.number().min(0).max(100).nullable().optional(),
  confidence: z.number().min(0).max(1).nullable().optional(),
  predicted_incremental_lift_pct: z.number().nullable().optional(),
  predicted_iroas: z.number().nullable().optional(),
  incremental_lift_ci_low: z.number().nullable().optional(),
  incremental_lift_ci_high: z.number().nullable().optional(),
  iroas_ci_low: z.number().nullable().optional(),
  iroas_ci_high: z.number().nullable().optional(),
  uncertainty_band: z.number().min(0).nullable().optional(),
  calibration_status: syntheticLiftCalibrationStatusSchema,
  calibration_observation_count: z.number().int().nonnegative(),
  calibration_last_updated_at: z.string().nullable().optional(),
  model_version: z.string().min(1),
  segment_scores: z.array(syntheticLiftPriorTimelineWindowSchema).default([]),
  feature_inputs: z.array(syntheticLiftPriorFeatureInputSchema).default([]),
  evidence_summary: z.string().min(1),
  signals_used: z.array(z.string().min(1)).default([])
});

const neuroScoreStatusSchema = z.enum(['available', 'unavailable', 'insufficient_data']);
const neuroScoreMachineNameSchema = z.enum([
  'arrest_score',
  'attentional_synchrony_index',
  'narrative_control_score',
  'blink_transport_score',
  'boundary_encoding_score',
  'reward_anticipation_index',
  'social_transmission_score',
  'self_relevance_score',
  'cta_reception_score',
  'synthetic_lift_prior',
  'au_friction_score'
]);
const neuroRollupMachineNameSchema = z.enum([
  'organic_reach_prior',
  'paid_lift_prior',
  'brand_memory_prior'
]);

const neuroEvidenceWindowSchema = z.object({
  start_ms: z.number().int().nonnegative(),
  end_ms: z.number().int().nonnegative(),
  reason: z.string().min(1)
});

const neuroFeatureContributionSchema = z.object({
  feature_name: z.string().min(1),
  contribution: z.number(),
  rationale: z.string().nullable().optional()
});

const neuroScoreContractSchema = z.object({
  machine_name: neuroScoreMachineNameSchema,
  display_label: z.string().min(1),
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  evidence_windows: z.array(neuroEvidenceWindowSchema),
  top_feature_contributions: z.array(neuroFeatureContributionSchema),
  model_version: z.string().min(1),
  provenance: z.string().min(1),
  claim_safe_description: z.string().min(1)
});

const neuroCompositeRollupSchema = z.object({
  machine_name: neuroRollupMachineNameSchema,
  display_label: z.string().min(1),
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  component_scores: z.array(neuroScoreMachineNameSchema),
  component_weights: z.record(z.string(), z.number()),
  model_version: z.string().min(1),
  provenance: z.string().min(1),
  claim_safe_description: z.string().min(1)
});

const neuroRegistryEntrySchema = z.object({
  machine_name: neuroScoreMachineNameSchema,
  display_label: z.string().min(1),
  claim_safe_description: z.string().min(1),
  builder_key: z.string().min(1)
});

const neuroRollupRegistryEntrySchema = z.object({
  machine_name: neuroRollupMachineNameSchema,
  display_label: z.string().min(1),
  claim_safe_description: z.string().min(1),
  builder_key: z.string().min(1)
});

const legacyScoreAdapterSchema = z.object({
  legacy_output: z.enum(['emotion', 'attention']),
  mapped_machine_name: neuroScoreMachineNameSchema,
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  notes: z.string().nullable().optional()
});

const neuroScoreTaxonomySchema = z.object({
  schema_version: z.string().min(1),
  scores: z.object({
    arrest_score: neuroScoreContractSchema,
    attentional_synchrony_index: neuroScoreContractSchema,
    narrative_control_score: neuroScoreContractSchema,
    blink_transport_score: neuroScoreContractSchema,
    boundary_encoding_score: neuroScoreContractSchema,
    reward_anticipation_index: neuroScoreContractSchema,
    social_transmission_score: neuroScoreContractSchema,
    self_relevance_score: neuroScoreContractSchema,
    cta_reception_score: neuroScoreContractSchema,
    synthetic_lift_prior: neuroScoreContractSchema,
    au_friction_score: neuroScoreContractSchema
  }),
  rollups: z.object({
    organic_reach_prior: neuroCompositeRollupSchema,
    paid_lift_prior: neuroCompositeRollupSchema,
    brand_memory_prior: neuroCompositeRollupSchema
  }),
  registry: z.array(neuroRegistryEntrySchema),
  rollup_registry: z.array(neuroRollupRegistryEntrySchema),
  legacy_score_adapters: z.array(legacyScoreAdapterSchema).optional().default([])
});

const productRollupModeSchema = z.enum(['creator', 'enterprise']);
const productRollupWarningSeveritySchema = z.enum(['low', 'medium', 'high']);
const productLiftTruthStatusSchema = z.enum(['unavailable', 'pending', 'measured']);

const productScoreSummarySchema = z.object({
  metric_key: z.string().min(1).max(64),
  display_label: z.string().min(1),
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  explanation: z.string().min(1),
  source_metrics: z.array(z.string().min(1)).default([])
});

const productRollupWarningSchema = z.object({
  warning_key: z.string().min(1).max(128),
  severity: productRollupWarningSeveritySchema,
  message: z.string().min(1),
  source_metrics: z.array(z.string().min(1)).default([])
});

const creatorProductRollupsSchema = z.object({
  reception_score: productScoreSummarySchema,
  organic_reach_prior: productScoreSummarySchema,
  explanations: z.array(z.string().min(1)).default([]),
  warnings: z.array(productRollupWarningSchema).default([])
});

const productLiftComparisonSchema = z.object({
  synthetic_lift_prior: productScoreSummarySchema,
  predicted_incremental_lift_pct: z.number().nullable().optional(),
  predicted_iroas: z.number().nullable().optional(),
  predicted_incremental_lift_ci_low: z.number().nullable().optional(),
  predicted_incremental_lift_ci_high: z.number().nullable().optional(),
  measured_lift_status: productLiftTruthStatusSchema,
  measured_incremental_lift_pct: z.number().nullable().optional(),
  measured_iroas: z.number().nullable().optional(),
  calibration_status: syntheticLiftCalibrationStatusSchema.nullable().optional(),
  note: z.string().min(1)
});

const enterpriseDecisionSupportSchema = z.object({
  media_team_summary: z.string().min(1),
  creative_team_summary: z.string().min(1)
});

const enterpriseProductRollupsSchema = z.object({
  paid_lift_prior: productScoreSummarySchema,
  brand_memory_prior: productScoreSummarySchema,
  cta_reception_score: productScoreSummarySchema,
  synthetic_lift_prior: productScoreSummarySchema,
  synthetic_vs_measured_lift: productLiftComparisonSchema,
  decision_support: enterpriseDecisionSupportSchema
});

const productRollupPresentationSchema = z
  .object({
    mode: productRollupModeSchema,
    workspace_tier: z.string().min(1).max(64),
    enabled_modes: z.array(productRollupModeSchema).default([]),
    mode_resolution_note: z.string().nullable().optional(),
    source_schema_version: z.string().min(1),
    creator: creatorProductRollupsSchema.nullable().optional(),
    enterprise: enterpriseProductRollupsSchema.nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (!value.enabled_modes.includes(value.mode)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['enabled_modes'],
        message: 'mode must be present in enabled_modes.'
      });
    }
    if (value.mode === 'creator' && !value.creator) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['creator'],
        message: 'creator payload must be provided when mode=creator.'
      });
    }
    if (value.mode === 'enterprise' && !value.enterprise) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['enterprise'],
        message: 'enterprise payload must be provided when mode=enterprise.'
      });
    }
  });

export const readoutPayloadSchema = z.object({
  schema_version: z.string().min(1),
  video_id: z.string().min(1),
  source_url: z.string().nullable().optional(),
  variant_id: z.string().nullable().optional(),
  session_id: z.string().min(1).nullable().optional(),
  aggregate: z.boolean(),
  duration_ms: z.number().int().nonnegative(),
  timebase: z.object({
    window_ms: z.number().int().positive(),
    step_ms: z.number().int().positive()
  }),
  context: z.object({
    scenes: z.array(readoutSceneSchema),
    cuts: z.array(readoutCutSchema),
    cta_markers: z.array(readoutCtaMarkerSchema)
  }),
  traces: z.object({
    attention_score: z.array(readoutTracePointSchema),
    attention_velocity: z.array(readoutTracePointSchema),
    blink_rate: z.array(readoutTracePointSchema),
    blink_inhibition: z.array(readoutTracePointSchema),
    reward_proxy: z.array(readoutTracePointSchema),
    valence_proxy: z.array(readoutTracePointSchema),
    arousal_proxy: z.array(readoutTracePointSchema),
    novelty_proxy: z.array(readoutTracePointSchema),
    tracking_confidence: z.array(readoutTracePointSchema),
    au_channels: z.array(readoutAuChannelSchema).optional().default([])
  }),
  segments: z.object({
    attention_gain_segments: z.array(readoutSegmentSchema),
    attention_loss_segments: z.array(readoutSegmentSchema),
    golden_scenes: z.array(readoutSegmentSchema),
    dead_zones: z.array(readoutSegmentSchema),
    confusion_segments: z.array(readoutSegmentSchema)
  }),
  labels: z.object({
    annotations: z.array(annotationSchema),
    survey_summary: surveySummarySchema.optional(),
    annotation_summary: annotationSummarySchema.optional()
  }),
  quality: z.object({
    session_quality_summary: readoutQualitySummarySchema,
    low_confidence_windows: z.array(readoutLowConfidenceWindowSchema)
  }),
  aggregate_metrics: z
    .object({
      attention_synchrony: z.number().min(-1).max(1).nullable().optional(),
      blink_synchrony: z.number().min(-1).max(1).nullable().optional(),
      grip_control_score: z.number().min(-1).max(1).nullable().optional(),
      attentional_synchrony: attentionalSynchronyDiagnosticsSchema.nullable().optional(),
      narrative_control: narrativeControlDiagnosticsSchema.nullable().optional(),
      reward_anticipation: rewardAnticipationDiagnosticsSchema.nullable().optional(),
      synthetic_lift_prior: syntheticLiftPriorDiagnosticsSchema.nullable().optional(),
      ci_method: z.enum(['sem_95']).nullable().optional(),
      included_sessions: z.number().int().nonnegative(),
      downweighted_sessions: z.number().int().nonnegative()
    })
    .nullable()
    .optional(),
  playback_telemetry: z.array(playbackTelemetryEventSchema).optional().default([]),
  neuro_scores: neuroScoreTaxonomySchema.nullable().optional(),
  product_rollups: productRollupPresentationSchema.nullable().optional(),
  legacy_score_adapters: z.array(legacyScoreAdapterSchema).optional().default([]),
  diagnostics: z.array(diagnosticCardSchema).optional().default([]),

  // Backward-compatible mirrors that may exist during migration.
  scenes: z.array(readoutSceneSchema).optional(),
  cuts: z.array(readoutCutSchema).optional(),
  cta_markers: z.array(readoutCtaMarkerSchema).optional(),
  quality_summary: readoutQualitySummarySchema.optional(),
  annotations: z.array(annotationSchema).optional(),
  annotation_summary: annotationSummarySchema.optional(),
  survey_summary: surveySummarySchema.optional()
});

export type ReadoutPayload = z.infer<typeof readoutPayloadSchema>;
