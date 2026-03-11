import { z } from 'zod';

export const attentionalSynchronyPathwaySchema = z.enum([
  'direct_panel_gaze',
  'fallback_proxy',
  'insufficient_data'
]);

export const attentionalSynchronyTimelineScoreSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    pathway: attentionalSynchronyPathwaySchema,
    reason: z.string().min(1)
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const attentionalSynchronyExtremaSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    reason: z.string().min(1)
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const attentionalSynchronyDiagnosticsSchema = z
  .object({
    pathway: attentionalSynchronyPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    segment_scores: z.array(attentionalSynchronyTimelineScoreSchema).default([]),
    peaks: z.array(attentionalSynchronyExtremaSchema).default([]),
    valleys: z.array(attentionalSynchronyExtremaSchema).default([]),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const narrativeControlPathwaySchema = z.enum([
  'timeline_grammar',
  'fallback_proxy',
  'insufficient_data'
]);

export const narrativeControlSceneScoreSchema = z
  .object({
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
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const narrativeControlMomentContributionSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    contribution: z.number(),
    category: z.string().min(1).max(64),
    reason: z.string().min(1),
    scene_id: z.string().nullable().optional(),
    cut_id: z.string().nullable().optional(),
    cta_id: z.string().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const narrativeControlHeuristicCheckSchema = z
  .object({
    heuristic_key: z.string().min(1).max(128),
    passed: z.boolean(),
    score_delta: z.number(),
    reason: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when heuristic window is provided.'
      });
    }
  });

export const narrativeControlDiagnosticsSchema = z
  .object({
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
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const blinkTransportPathwaySchema = z.enum([
  'direct_panel_blink',
  'fallback_proxy',
  'sparse_fallback',
  'insufficient_data',
  'disabled'
]);

export const blinkTransportTimelineScoreSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    pathway: blinkTransportPathwaySchema,
    reason: z.string().min(1),
    blink_suppression: z.number().min(0).max(1).nullable().optional(),
    rebound_signal: z.number().min(0).max(1).nullable().optional(),
    cta_avoidance_signal: z.number().min(0).max(1).nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const blinkTransportWarningSeveritySchema = z.enum(['low', 'medium', 'high']);

export const blinkTransportWarningSchema = z
  .object({
    warning_key: z.string().min(1).max(128),
    severity: blinkTransportWarningSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const blinkTransportDiagnosticsSchema = z
  .object({
    pathway: blinkTransportPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    segment_scores: z.array(blinkTransportTimelineScoreSchema).default([]),
    suppression_score: z.number().min(0).max(1).nullable().optional(),
    rebound_score: z.number().min(0).max(1).nullable().optional(),
    cta_avoidance_score: z.number().min(0).max(1).nullable().optional(),
    cross_viewer_blink_synchrony: z.number().min(-1).max(1).nullable().optional(),
    engagement_warnings: z.array(blinkTransportWarningSchema).default([]),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data' && value.pathway !== 'disabled') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const rewardAnticipationPathwaySchema = z.enum([
  'timeline_dynamics',
  'fallback_proxy',
  'insufficient_data'
]);

export const rewardAnticipationTimelineWindowTypeSchema = z.enum([
  'anticipation_ramp',
  'payoff_window'
]);

export const rewardAnticipationTimelineWindowSchema = z
  .object({
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
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const rewardAnticipationWarningSeveritySchema = z.enum(['low', 'medium', 'high']);

export const rewardAnticipationWarningSchema = z
  .object({
    warning_key: z.string().min(1).max(128),
    severity: rewardAnticipationWarningSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const rewardAnticipationDiagnosticsSchema = z
  .object({
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
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const boundaryEncodingPathwaySchema = z.enum([
  'timeline_boundary_model',
  'fallback_proxy',
  'insufficient_data'
]);

export const boundaryEncodingTimelineWindowTypeSchema = z.enum([
  'strong_encoding',
  'weak_encoding'
]);

export const boundaryEncodingTimelineWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    window_type: boundaryEncodingTimelineWindowTypeSchema,
    reason: z.string().min(1),
    payload_type: z.string().nullable().optional(),
    nearest_boundary_ms: z.number().int().nonnegative().nullable().optional(),
    boundary_distance_ms: z.number().int().nonnegative().nullable().optional(),
    novelty_signal: z.number().min(0).max(1).nullable().optional(),
    reinforcement_signal: z.number().min(0).max(1).nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const boundaryEncodingFlagSeveritySchema = z.enum(['low', 'medium', 'high']);

export const boundaryEncodingFlagSchema = z
  .object({
    flag_key: z.string().min(1).max(128),
    severity: boundaryEncodingFlagSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const boundaryEncodingDiagnosticsSchema = z
  .object({
    pathway: boundaryEncodingPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    strong_windows: z.array(boundaryEncodingTimelineWindowSchema).default([]),
    weak_windows: z.array(boundaryEncodingTimelineWindowSchema).default([]),
    flags: z.array(boundaryEncodingFlagSchema).default([]),
    boundary_alignment_score: z.number().min(0).max(1).nullable().optional(),
    novelty_boundary_score: z.number().min(0).max(1).nullable().optional(),
    reinforcement_score: z.number().min(0).max(1).nullable().optional(),
    overload_risk_score: z.number().min(0).max(1).nullable().optional(),
    payload_count: z.number().int().nonnegative(),
    boundary_count: z.number().int().nonnegative(),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const socialTransmissionPathwaySchema = z.enum([
  'annotation_augmented',
  'timeline_signal_model',
  'fallback_proxy',
  'insufficient_data'
]);

export const socialTransmissionTimelineWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    reason: z.string().min(1),
    novelty_signal: z.number().min(0).max(1).nullable().optional(),
    emotional_activation_signal: z.number().min(0).max(1).nullable().optional(),
    quote_worthiness_signal: z.number().min(0).max(1).nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const socialTransmissionDiagnosticsSchema = z
  .object({
    pathway: socialTransmissionPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    segment_scores: z.array(socialTransmissionTimelineWindowSchema).default([]),
    novelty_signal: z.number().min(0).max(1).nullable().optional(),
    identity_signal: z.number().min(0).max(1).nullable().optional(),
    usefulness_signal: z.number().min(0).max(1).nullable().optional(),
    quote_worthiness_signal: z.number().min(0).max(1).nullable().optional(),
    emotional_activation_signal: z.number().min(0).max(1).nullable().optional(),
    memorability_signal: z.number().min(0).max(1).nullable().optional(),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const selfRelevancePathwaySchema = z.enum([
  'contextual_personalization',
  'survey_augmented',
  'fallback_proxy',
  'insufficient_data'
]);

export const selfRelevanceTimelineWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    reason: z.string().min(1),
    direct_address_signal: z.number().min(0).max(1).nullable().optional(),
    personalization_hook_signal: z.number().min(0).max(1).nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const selfRelevanceWarningSeveritySchema = z.enum(['low', 'medium', 'high']);

export const selfRelevanceWarningSchema = z
  .object({
    warning_key: z.string().min(1).max(128),
    severity: selfRelevanceWarningSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const selfRelevanceDiagnosticsSchema = z
  .object({
    pathway: selfRelevancePathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    segment_scores: z.array(selfRelevanceTimelineWindowSchema).default([]),
    warnings: z.array(selfRelevanceWarningSchema).default([]),
    direct_address_signal: z.number().min(0).max(1).nullable().optional(),
    audience_match_signal: z.number().min(0).max(1).nullable().optional(),
    niche_specificity_signal: z.number().min(0).max(1).nullable().optional(),
    personalization_hook_signal: z.number().min(0).max(1).nullable().optional(),
    resonance_signal: z.number().min(0).max(1).nullable().optional(),
    context_coverage: z.number().min(0).max(1).nullable().optional(),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const syntheticLiftPriorPathwaySchema = z.enum([
  'taxonomy_regression',
  'fallback_proxy',
  'insufficient_data'
]);

export const syntheticLiftCalibrationStatusSchema = z.enum([
  'uncalibrated',
  'provisional',
  'geox_calibrated',
  'truth_layer_unavailable'
]);

export const syntheticLiftPriorFeatureInputSourceSchema = z.enum([
  'taxonomy',
  'legacy_performance',
  'calibration'
]);

export const syntheticLiftPriorFeatureInputSchema = z.object({
  feature_name: z.string().min(1).max(128),
  source: syntheticLiftPriorFeatureInputSourceSchema,
  raw_value: z.number(),
  normalized_value: z.number().min(0).max(1),
  weight: z.number().min(0)
});

export const syntheticLiftPriorTimelineWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    reason: z.string().min(1),
    contribution: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const syntheticLiftPriorDiagnosticsSchema = z
  .object({
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
    calibration_status: syntheticLiftCalibrationStatusSchema.default('uncalibrated'),
    calibration_observation_count: z.number().int().nonnegative().default(0),
    calibration_last_updated_at: z.string().min(1).nullable().optional(),
    model_version: z.string().min(1),
    segment_scores: z.array(syntheticLiftPriorTimelineWindowSchema).default([]),
    feature_inputs: z.array(syntheticLiftPriorFeatureInputSchema).default([]),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
      if (
        value.predicted_incremental_lift_pct === null ||
        value.predicted_incremental_lift_pct === undefined
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['predicted_incremental_lift_pct'],
          message: 'predicted_incremental_lift_pct must be present when pathway has data.'
        });
      }
      if (value.predicted_iroas === null || value.predicted_iroas === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['predicted_iroas'],
          message: 'predicted_iroas must be present when pathway has data.'
        });
      }
      if (
        value.incremental_lift_ci_low === null ||
        value.incremental_lift_ci_low === undefined ||
        value.incremental_lift_ci_high === null ||
        value.incremental_lift_ci_high === undefined
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['incremental_lift_ci_low'],
          message: 'incremental_lift_ci_low/high must be present when pathway has data.'
        });
      }
      if (
        value.iroas_ci_low === null ||
        value.iroas_ci_low === undefined ||
        value.iroas_ci_high === null ||
        value.iroas_ci_high === undefined
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['iroas_ci_low'],
          message: 'iroas_ci_low/high must be present when pathway has data.'
        });
      }
    }
    if (
      value.incremental_lift_ci_low != null &&
      value.incremental_lift_ci_high != null &&
      value.incremental_lift_ci_low > value.incremental_lift_ci_high
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['incremental_lift_ci_low'],
        message: 'incremental_lift_ci_low must be less than or equal to incremental_lift_ci_high.'
      });
    }
    if (value.iroas_ci_low != null && value.iroas_ci_high != null && value.iroas_ci_low > value.iroas_ci_high) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['iroas_ci_low'],
        message: 'iroas_ci_low must be less than or equal to iroas_ci_high.'
      });
    }
  });

export const auFrictionPathwaySchema = z.enum([
  'au_signal_model',
  'fallback_proxy',
  'insufficient_data'
]);

export const auFrictionStateSchema = z.enum([
  'confusion',
  'strain',
  'amusement',
  'tension',
  'resistance'
]);

export const auFrictionTimelineWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    reason: z.string().min(1),
    dominant_state: auFrictionStateSchema,
    transition_context: z.enum(['post_transition_spike']).nullable().optional(),
    au04_signal: z.number().min(0).max(1).nullable().optional(),
    au06_signal: z.number().min(0).max(1).nullable().optional(),
    au12_signal: z.number().min(0).max(1).nullable().optional(),
    au25_signal: z.number().min(0).max(1).nullable().optional(),
    au26_signal: z.number().min(0).max(1).nullable().optional(),
    au45_signal: z.number().min(0).max(1).nullable().optional(),
    confusion_signal: z.number().min(0).max(1).nullable().optional(),
    strain_signal: z.number().min(0).max(1).nullable().optional(),
    amusement_signal: z.number().min(0).max(1).nullable().optional(),
    tension_signal: z.number().min(0).max(1).nullable().optional(),
    resistance_signal: z.number().min(0).max(1).nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const auFrictionQualityWarningSeveritySchema = z.enum(['low', 'medium', 'high']);

export const auFrictionQualityWarningSchema = z
  .object({
    warning_key: z.string().min(1).max(128),
    severity: auFrictionQualityWarningSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const auFrictionDiagnosticsSchema = z
  .object({
    pathway: auFrictionPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    segment_scores: z.array(auFrictionTimelineWindowSchema).default([]),
    warnings: z.array(auFrictionQualityWarningSchema).default([]),
    confusion_signal: z.number().min(0).max(1).nullable().optional(),
    strain_signal: z.number().min(0).max(1).nullable().optional(),
    amusement_signal: z.number().min(0).max(1).nullable().optional(),
    tension_signal: z.number().min(0).max(1).nullable().optional(),
    resistance_signal: z.number().min(0).max(1).nullable().optional(),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });

export const ctaReceptionPathwaySchema = z.enum([
  'multi_signal_model',
  'fallback_proxy',
  'insufficient_data'
]);

export const ctaReceptionTimelineWindowSchema = z
  .object({
    cta_id: z.string().nullable().optional(),
    cta_type: z.string().min(1).max(64),
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    score: z.number().min(0).max(100),
    confidence: z.number().min(0).max(1),
    reason: z.string().min(1),
    synchrony_support: z.number().min(0).max(1).nullable().optional(),
    narrative_support: z.number().min(0).max(1).nullable().optional(),
    blink_receptivity_support: z.number().min(0).max(1).nullable().optional(),
    reward_timing_support: z.number().min(0).max(1).nullable().optional(),
    boundary_coherence_support: z.number().min(0).max(1).nullable().optional(),
    timing_fit_support: z.number().min(0).max(1).nullable().optional(),
    flag_keys: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms.'
      });
    }
  });

export const ctaReceptionFlagSeveritySchema = z.enum(['low', 'medium', 'high']);

export const ctaReceptionFlagSchema = z
  .object({
    flag_key: z.string().min(1).max(128),
    severity: ctaReceptionFlagSeveritySchema,
    message: z.string().min(1),
    start_ms: z.number().int().nonnegative().nullable().optional(),
    end_ms: z.number().int().positive().nullable().optional(),
    cta_id: z.string().nullable().optional(),
    cta_type: z.string().nullable().optional(),
    metric_value: z.number().nullable().optional()
  })
  .superRefine((value, ctx) => {
    if (value.start_ms != null && value.end_ms != null && value.end_ms <= value.start_ms) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_ms'],
        message: 'end_ms must be greater than start_ms when warning window is provided.'
      });
    }
  });

export const ctaReceptionDiagnosticsSchema = z
  .object({
    pathway: ctaReceptionPathwaySchema,
    global_score: z.number().min(0).max(100).nullable().optional(),
    confidence: z.number().min(0).max(1).nullable().optional(),
    cta_windows: z.array(ctaReceptionTimelineWindowSchema).default([]),
    flags: z.array(ctaReceptionFlagSchema).default([]),
    synchrony_support: z.number().min(0).max(1).nullable().optional(),
    narrative_support: z.number().min(0).max(1).nullable().optional(),
    blink_receptivity_support: z.number().min(0).max(1).nullable().optional(),
    reward_timing_support: z.number().min(0).max(1).nullable().optional(),
    boundary_coherence_support: z.number().min(0).max(1).nullable().optional(),
    overload_risk_support: z.number().min(0).max(1).nullable().optional(),
    evidence_summary: z.string().min(1),
    signals_used: z.array(z.string().min(1)).default([])
  })
  .superRefine((value, ctx) => {
    if (value.pathway !== 'insufficient_data') {
      if (value.global_score === null || value.global_score === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['global_score'],
          message: 'global_score must be present when pathway has data.'
        });
      }
      if (value.confidence === null || value.confidence === undefined) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when pathway has data.'
        });
      }
    }
  });
export const readoutAggregateMetricsSchema = z.object({
  attention_synchrony: z.number().min(-1).max(1).nullable().optional(),
  blink_synchrony: z.number().min(-1).max(1).nullable().optional(),
  grip_control_score: z.number().min(-1).max(1).nullable().optional(),
  attentional_synchrony: attentionalSynchronyDiagnosticsSchema.nullable().optional(),
  narrative_control: narrativeControlDiagnosticsSchema.nullable().optional(),
  blink_transport: blinkTransportDiagnosticsSchema.nullable().optional(),
  reward_anticipation: rewardAnticipationDiagnosticsSchema.nullable().optional(),
  boundary_encoding: boundaryEncodingDiagnosticsSchema.nullable().optional(),
  au_friction: auFrictionDiagnosticsSchema.nullable().optional(),
  cta_reception: ctaReceptionDiagnosticsSchema.nullable().optional(),
  social_transmission: socialTransmissionDiagnosticsSchema.nullable().optional(),
  self_relevance: selfRelevanceDiagnosticsSchema.nullable().optional(),
  synthetic_lift_prior: syntheticLiftPriorDiagnosticsSchema.nullable().optional(),
  ci_method: z.enum(['sem_95']).nullable().optional(),
  included_sessions: z.number().int().nonnegative(),
  downweighted_sessions: z.number().int().nonnegative()
});

export type AttentionalSynchronyPathway = z.infer<typeof attentionalSynchronyPathwaySchema>;
export type AttentionalSynchronyTimelineScore = z.infer<typeof attentionalSynchronyTimelineScoreSchema>;
export type AttentionalSynchronyExtrema = z.infer<typeof attentionalSynchronyExtremaSchema>;
export type AttentionalSynchronyDiagnostics = z.infer<typeof attentionalSynchronyDiagnosticsSchema>;
export type NarrativeControlPathway = z.infer<typeof narrativeControlPathwaySchema>;
export type NarrativeControlSceneScore = z.infer<typeof narrativeControlSceneScoreSchema>;
export type NarrativeControlMomentContribution = z.infer<typeof narrativeControlMomentContributionSchema>;
export type NarrativeControlHeuristicCheck = z.infer<typeof narrativeControlHeuristicCheckSchema>;
export type NarrativeControlDiagnostics = z.infer<typeof narrativeControlDiagnosticsSchema>;
export type BlinkTransportPathway = z.infer<typeof blinkTransportPathwaySchema>;
export type BlinkTransportTimelineScore = z.infer<typeof blinkTransportTimelineScoreSchema>;
export type BlinkTransportWarningSeverity = z.infer<typeof blinkTransportWarningSeveritySchema>;
export type BlinkTransportWarning = z.infer<typeof blinkTransportWarningSchema>;
export type BlinkTransportDiagnostics = z.infer<typeof blinkTransportDiagnosticsSchema>;
export type RewardAnticipationPathway = z.infer<typeof rewardAnticipationPathwaySchema>;
export type RewardAnticipationTimelineWindowType = z.infer<typeof rewardAnticipationTimelineWindowTypeSchema>;
export type RewardAnticipationTimelineWindow = z.infer<typeof rewardAnticipationTimelineWindowSchema>;
export type RewardAnticipationWarningSeverity = z.infer<typeof rewardAnticipationWarningSeveritySchema>;
export type RewardAnticipationWarning = z.infer<typeof rewardAnticipationWarningSchema>;
export type RewardAnticipationDiagnostics = z.infer<typeof rewardAnticipationDiagnosticsSchema>;
export type BoundaryEncodingPathway = z.infer<typeof boundaryEncodingPathwaySchema>;
export type BoundaryEncodingTimelineWindowType = z.infer<typeof boundaryEncodingTimelineWindowTypeSchema>;
export type BoundaryEncodingTimelineWindow = z.infer<typeof boundaryEncodingTimelineWindowSchema>;
export type BoundaryEncodingFlagSeverity = z.infer<typeof boundaryEncodingFlagSeveritySchema>;
export type BoundaryEncodingFlag = z.infer<typeof boundaryEncodingFlagSchema>;
export type BoundaryEncodingDiagnostics = z.infer<typeof boundaryEncodingDiagnosticsSchema>;
export type SocialTransmissionPathway = z.infer<typeof socialTransmissionPathwaySchema>;
export type SocialTransmissionTimelineWindow = z.infer<typeof socialTransmissionTimelineWindowSchema>;
export type SocialTransmissionDiagnostics = z.infer<typeof socialTransmissionDiagnosticsSchema>;
export type SelfRelevancePathway = z.infer<typeof selfRelevancePathwaySchema>;
export type SelfRelevanceTimelineWindow = z.infer<typeof selfRelevanceTimelineWindowSchema>;
export type SelfRelevanceWarningSeverity = z.infer<typeof selfRelevanceWarningSeveritySchema>;
export type SelfRelevanceWarning = z.infer<typeof selfRelevanceWarningSchema>;
export type SelfRelevanceDiagnostics = z.infer<typeof selfRelevanceDiagnosticsSchema>;
export type SyntheticLiftPriorPathway = z.infer<typeof syntheticLiftPriorPathwaySchema>;
export type SyntheticLiftCalibrationStatus = z.infer<typeof syntheticLiftCalibrationStatusSchema>;
export type SyntheticLiftPriorFeatureInputSource = z.infer<typeof syntheticLiftPriorFeatureInputSourceSchema>;
export type SyntheticLiftPriorFeatureInput = z.infer<typeof syntheticLiftPriorFeatureInputSchema>;
export type SyntheticLiftPriorTimelineWindow = z.infer<typeof syntheticLiftPriorTimelineWindowSchema>;
export type SyntheticLiftPriorDiagnostics = z.infer<typeof syntheticLiftPriorDiagnosticsSchema>;
export type AuFrictionPathway = z.infer<typeof auFrictionPathwaySchema>;
export type AuFrictionState = z.infer<typeof auFrictionStateSchema>;
export type AuFrictionTimelineWindow = z.infer<typeof auFrictionTimelineWindowSchema>;
export type AuFrictionQualityWarningSeverity = z.infer<typeof auFrictionQualityWarningSeveritySchema>;
export type AuFrictionQualityWarning = z.infer<typeof auFrictionQualityWarningSchema>;
export type AuFrictionDiagnostics = z.infer<typeof auFrictionDiagnosticsSchema>;
export type CtaReceptionPathway = z.infer<typeof ctaReceptionPathwaySchema>;
export type CtaReceptionTimelineWindow = z.infer<typeof ctaReceptionTimelineWindowSchema>;
export type CtaReceptionFlagSeverity = z.infer<typeof ctaReceptionFlagSeveritySchema>;
export type CtaReceptionFlag = z.infer<typeof ctaReceptionFlagSchema>;
export type CtaReceptionDiagnostics = z.infer<typeof ctaReceptionDiagnosticsSchema>;
export type ReadoutAggregateMetrics = z.infer<typeof readoutAggregateMetricsSchema>;
