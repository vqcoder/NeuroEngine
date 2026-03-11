import { z } from 'zod';

const browserMetadataSchema = z.object({
  userAgent: z.string().min(1),
  platform: z.string().min(1),
  language: z.string().min(1),
  viewport: z.object({
    width: z.number().int().positive(),
    height: z.number().int().positive()
  }),
  timezone: z.string().min(1),
  hardwareConcurrency: z.number().int().nonnegative()
});

const eventSchema = z.object({
  type: z.enum([
    'consent_accepted',
    'webcam_granted',
    'webcam_denied',
    'quality_check',
    'playback_started',
    'survey_answered',
    'play',
    'pause',
    'seek_start',
    'seek_end',
    'seek',
    'rewind',
    'mute',
    'unmute',
    'volume_change',
    'fullscreen_enter',
    'fullscreen_exit',
    'visibility_hidden',
    'visibility_visible',
    'window_blur',
    'window_focus',
    'annotation_mode_entered',
    'annotation_mode_skipped',
    'annotation_tag_set',
    'ended',
    'abandonment',
    'session_incomplete',
    'finish_clicked',
    'upload_success',
    'upload_failed'
  ]),
  sessionId: z.string().uuid(),
  videoId: z.string().min(1),
  wallTimeMs: z.number().int().nonnegative(),
  clientMonotonicMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative(),
  details: z.record(z.string(), z.unknown()).optional()
});

const dialSampleSchema = z.object({
  id: z.string().uuid(),
  wallTimeMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative(),
  value: z.number().min(0).max(100)
});

const annotationMarkerSchema = z.object({
  id: z.string().uuid(),
  sessionId: z.string().uuid(),
  videoId: z.string().min(1),
  markerType: z.enum([
    'engaging_moment',
    'confusing_moment',
    'stop_watching_moment',
    'cta_landed_moment'
  ]),
  videoTimeMs: z.number().int().nonnegative(),
  note: z.string().max(2000).nullable().optional(),
  createdAt: z.string().datetime()
});

const surveyResponseSchema = z
  .object({
    questionKey: z.string().min(1),
    responseText: z.string().optional(),
    responseNumber: z.number().optional(),
    responseJson: z.record(z.any()).optional()
  })
  .superRefine((payload, ctx) => {
    const hasNumber = typeof payload.responseNumber === 'number';
    const hasText = typeof payload.responseText === 'string';
    const hasJson = typeof payload.responseJson === 'object';
    if (!hasNumber && !hasText && !hasJson) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Survey response must include a number, text, or JSON payload.'
      });
    }
  });

export const sessionBundleSchema = z.object({
  studyId: z.string().min(1),
  videoId: z.string().min(1),
  participantId: z.string().uuid(),
  browserMetadata: browserMetadataSchema,
  eventTimeline: z.array(eventSchema),
  dialSamples: z.array(dialSampleSchema).default([]),
  annotations: z.array(annotationMarkerSchema).default([]),
  annotationSkipped: z.boolean().default(false),
  surveyResponses: z.array(surveyResponseSchema).default([]),
  frames: z
    .array(
      z.object({
        id: z.string().uuid(),
        timestampMs: z.number().int().nonnegative(),
        videoTimeMs: z.number().int().nonnegative().optional(),
        jpegBase64: z.string().min(16)
      })
    )
    .default([]),
  framePointers: z
    .array(
      z.object({
        id: z.string().uuid(),
        timestampMs: z.number().int().nonnegative(),
        videoTimeMs: z.number().int().nonnegative().optional(),
        pointer: z.string().min(1)
      })
    )
    .default([])
}).superRefine((payload, ctx) => {
  if (payload.frames.length === 0 && payload.framePointers.length === 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['frames'],
      message: 'Payload must include frames or frame pointers.'
    });
  }
});

export type SessionBundle = z.infer<typeof sessionBundleSchema>;
