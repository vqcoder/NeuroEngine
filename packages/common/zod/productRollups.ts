import { z } from 'zod';
import { neuroScoreStatusSchema } from './neuroScoreTaxonomy';

export const productRollupModeSchema = z.enum(['creator', 'enterprise']);
export const productRollupWarningSeveritySchema = z.enum(['low', 'medium', 'high']);
export const productLiftTruthStatusSchema = z.enum(['unavailable', 'pending', 'measured']);
export const syntheticLiftCalibrationStatusSchema = z.enum([
  'uncalibrated',
  'provisional',
  'geox_calibrated',
  'truth_layer_unavailable'
]);

export const productScoreSummarySchema = z.object({
  metric_key: z.string().min(1).max(64),
  display_label: z.string().min(1),
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  explanation: z.string().min(1),
  source_metrics: z.array(z.string().min(1)).default([])
});

export const productRollupWarningSchema = z.object({
  warning_key: z.string().min(1).max(128),
  severity: productRollupWarningSeveritySchema,
  message: z.string().min(1),
  source_metrics: z.array(z.string().min(1)).default([])
});

export const creatorProductRollupsSchema = z.object({
  reception_score: productScoreSummarySchema,
  organic_reach_prior: productScoreSummarySchema,
  explanations: z.array(z.string().min(1)).default([]),
  warnings: z.array(productRollupWarningSchema).default([])
});

export const productLiftComparisonSchema = z.object({
  synthetic_lift_prior: productScoreSummarySchema,
  predicted_incremental_lift_pct: z.number().nullable().optional(),
  predicted_iroas: z.number().nullable().optional(),
  predicted_incremental_lift_ci_low: z.number().nullable().optional(),
  predicted_incremental_lift_ci_high: z.number().nullable().optional(),
  measured_lift_status: productLiftTruthStatusSchema.default('unavailable'),
  measured_incremental_lift_pct: z.number().nullable().optional(),
  measured_iroas: z.number().nullable().optional(),
  calibration_status: syntheticLiftCalibrationStatusSchema.nullable().optional(),
  note: z.string().min(1)
});

export const enterpriseDecisionSupportSchema = z.object({
  media_team_summary: z.string().min(1),
  creative_team_summary: z.string().min(1)
});

export const enterpriseProductRollupsSchema = z.object({
  paid_lift_prior: productScoreSummarySchema,
  brand_memory_prior: productScoreSummarySchema,
  cta_reception_score: productScoreSummarySchema,
  synthetic_lift_prior: productScoreSummarySchema,
  synthetic_vs_measured_lift: productLiftComparisonSchema,
  decision_support: enterpriseDecisionSupportSchema
});

export const productRollupPresentationSchema = z
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

export type ProductRollupPresentation = z.infer<typeof productRollupPresentationSchema>;
