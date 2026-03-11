import { z } from 'zod';

export const neuroScoreMachineNames = [
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
] as const;

export const neuroRollupMachineNames = [
  'organic_reach_prior',
  'paid_lift_prior',
  'brand_memory_prior'
] as const;

export const neuroScoreStatusSchema = z.enum([
  'available',
  'unavailable',
  'insufficient_data'
]);

export const neuroEvidenceWindowSchema = z
  .object({
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().nonnegative(),
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

export const neuroFeatureContributionSchema = z.object({
  feature_name: z.string().min(1),
  contribution: z.number(),
  rationale: z.string().min(1).nullable().optional()
});

export const neuroScoreContractSchema = z
  .object({
    machine_name: z.enum(neuroScoreMachineNames),
    display_label: z.string().min(1),
    scalar_value: z.number().min(0).max(100).nullable(),
    confidence: z.number().min(0).max(1).nullable(),
    status: neuroScoreStatusSchema,
    evidence_windows: z.array(neuroEvidenceWindowSchema),
    top_feature_contributions: z.array(neuroFeatureContributionSchema),
    model_version: z.string().min(1),
    provenance: z.string().min(1),
    claim_safe_description: z.string().min(1)
  })
  .superRefine((value, ctx) => {
    if (value.status === 'available') {
      if (value.scalar_value === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['scalar_value'],
          message: 'scalar_value must be present when status=available.'
        });
      }
      if (value.confidence === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when status=available.'
        });
      }
    }
  });

export const neuroCompositeRollupSchema = z
  .object({
    machine_name: z.enum(neuroRollupMachineNames),
    display_label: z.string().min(1),
    scalar_value: z.number().min(0).max(100).nullable(),
    confidence: z.number().min(0).max(1).nullable(),
    status: neuroScoreStatusSchema,
    component_scores: z.array(z.enum(neuroScoreMachineNames)),
    component_weights: z.record(z.string(), z.number()),
    model_version: z.string().min(1),
    provenance: z.string().min(1),
    claim_safe_description: z.string().min(1)
  })
  .superRefine((value, ctx) => {
    if (value.status === 'available') {
      if (value.scalar_value === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['scalar_value'],
          message: 'scalar_value must be present when status=available.'
        });
      }
      if (value.confidence === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['confidence'],
          message: 'confidence must be present when status=available.'
        });
      }
    }
  });

export const legacyScoreAdapterSchema = z.object({
  legacy_output: z.enum(['emotion', 'attention']),
  mapped_machine_name: z.enum(neuroScoreMachineNames),
  scalar_value: z.number().min(0).max(100).nullable(),
  confidence: z.number().min(0).max(1).nullable(),
  status: neuroScoreStatusSchema,
  notes: z.string().nullable().optional()
});

export const neuroScoreRegistryEntrySchema = z.object({
  machine_name: z.enum(neuroScoreMachineNames),
  display_label: z.string().min(1),
  claim_safe_description: z.string().min(1),
  builder_key: z.string().min(1)
});

export const neuroRollupRegistryEntrySchema = z.object({
  machine_name: z.enum(neuroRollupMachineNames),
  display_label: z.string().min(1),
  claim_safe_description: z.string().min(1),
  builder_key: z.string().min(1)
});

export const neuroScoreTaxonomySchema = z.object({
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
  registry: z.array(neuroScoreRegistryEntrySchema),
  rollup_registry: z.array(neuroRollupRegistryEntrySchema),
  legacy_score_adapters: z.array(legacyScoreAdapterSchema).default([])
});

export type NeuroScoreMachineName = (typeof neuroScoreMachineNames)[number];
export type NeuroRollupMachineName = (typeof neuroRollupMachineNames)[number];
export type NeuroScoreStatus = z.infer<typeof neuroScoreStatusSchema>;
export type NeuroScoreContract = z.infer<typeof neuroScoreContractSchema>;
export type NeuroCompositeRollup = z.infer<typeof neuroCompositeRollupSchema>;
export type LegacyScoreAdapter = z.infer<typeof legacyScoreAdapterSchema>;
export type NeuroScoreTaxonomy = z.infer<typeof neuroScoreTaxonomySchema>;
