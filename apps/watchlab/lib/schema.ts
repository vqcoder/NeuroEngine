import { z } from 'zod';

export const browserMetadataSchema = z.object({
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

export const timelineEventSchema = z.object({
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
    'survey_chat_message_sent',
    'survey_chat_message_received',
    'survey_chat_error',
    'webcam_capture_stopped',
    'webcam_device_lost',
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

export const uploadFrameSchema = z.object({
  id: z.string().uuid(),
  timestampMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative().optional(),
  jpegBase64: z.string().min(16)
});

export const framePointerSchema = z.object({
  id: z.string().uuid(),
  timestampMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative().optional(),
  pointer: z.string().min(1)
});

export const dialSampleSchema = z.object({
  id: z.string().uuid(),
  wallTimeMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative(),
  value: z.number().min(0).max(100)
});

export const qualitySampleSchema = z.object({
  id: z.string().uuid(),
  wallTimeMs: z.number().int().nonnegative(),
  videoTimeMs: z.number().int().nonnegative(),
  sampleWindowMs: z.number().int().positive(),
  brightness: z.number(),
  brightnessScore: z.number().min(0).max(1),
  blur: z.number().nonnegative(),
  blurScore: z.number().min(0).max(1),
  fps: z.number().nonnegative(),
  fpsStability: z.number().min(0).max(1),
  faceDetected: z.boolean(),
  faceVisiblePct: z.number().min(0).max(1),
  headPoseValidPct: z.number().min(0).max(1),
  occlusionScore: z.number().min(0).max(1),
  qualityScore: z.number().min(0).max(1),
  trackingConfidence: z.number().min(0).max(1),
  qualityFlags: z
    .array(z.enum(['low_light', 'blur', 'face_lost', 'high_yaw_pitch']))
    .default([])
});

const traceAuDefaults = {
  AU04: 0,
  AU06: 0,
  AU12: 0,
  AU45: 0,
  AU25: 0,
  AU26: 0
} as const;

export const traceRowSchema = z
  .object({
    t_ms: z.number().int().nonnegative().optional(),
    video_time_ms: z.number().int().nonnegative().optional(),
    scene_id: z.string().min(1).optional(),
    cut_id: z.string().min(1).optional(),
    cta_id: z.string().min(1).optional(),
    face_ok: z.boolean(),
    face_presence_confidence: z.number().min(0).max(1).optional(),
    brightness: z.number(),
    blur: z.number().nonnegative().optional(),
    landmarks_ok: z.boolean(),
    landmarks_confidence: z.number().min(0).max(1).optional(),
    eye_openness: z.number().min(0).max(1).optional(),
    blink: z.union([z.literal(0), z.literal(1)]),
    blink_confidence: z.number().min(0).max(1).optional(),
    rolling_blink_rate: z.number().nonnegative().optional(),
    blink_inhibition_score: z.number().min(-1).max(1).optional(),
    blink_inhibition_active: z.boolean().optional(),
    blink_baseline_rate: z.number().nonnegative().optional(),
    dial: z.number().min(0).max(100).optional(),
    reward_proxy: z.number().min(0).max(100).optional(),
    au: z.record(z.string(), z.number()).default(traceAuDefaults),
    au_norm: z.record(z.string(), z.number()).default(traceAuDefaults),
    au_confidence: z.number().min(0).max(1).optional(),
    head_pose: z
      .object({
        yaw: z.number().nullable().optional(),
        pitch: z.number().nullable().optional(),
        roll: z.number().nullable().optional()
      })
      .default({ yaw: null, pitch: null, roll: null }),
    head_pose_confidence: z.number().min(0).max(1).optional(),
    head_pose_valid_pct: z.number().min(0).max(1).optional(),
    gaze_on_screen_proxy: z.number().min(0).max(1).optional(),
    gaze_on_screen_confidence: z.number().min(0).max(1).optional(),
    fps: z.number().nonnegative().optional(),
    fps_stability: z.number().min(0).max(1).optional(),
    face_visible_pct: z.number().min(0).max(1).optional(),
    occlusion_score: z.number().min(0).max(1).optional(),
    quality_score: z.number().min(0).max(1).optional(),
    quality_confidence: z.number().min(0).max(1).optional(),
    tracking_confidence: z.number().min(0).max(1).optional(),
    quality_flags: z.array(z.string()).default([])
  })
  .superRefine((row, ctx) => {
    if (row.video_time_ms === undefined && row.t_ms === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Trace rows require video_time_ms or t_ms for canonical timeline alignment.'
      });
    }
  })
  .transform((row) => ({
    ...row,
    video_time_ms: row.video_time_ms ?? row.t_ms ?? 0,
    t_ms: row.t_ms ?? row.video_time_ms ?? 0
  }));

export const sessionQualitySummarySchema = z.object({
  sampleCount: z.number().int().nonnegative(),
  meanTrackingConfidence: z.number().min(0).max(1),
  meanQualityScore: z.number().min(0).max(1),
  lowConfidenceWindowCount: z.number().int().nonnegative(),
  usableSeconds: z.number().nonnegative()
});

export const annotationMarkerSchema = z.object({
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

export const surveyResponseSchema = z
  .object({
    questionKey: z.string().min(1),
    responseNumber: z.number().optional(),
    responseText: z.string().optional(),
    responseJson: z.record(z.string(), z.unknown()).optional()
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

export const uploadPayloadSchema = z
  .object({
    studyId: z.string().min(1),
    videoId: z.string().min(1),
    sourceUrl: z.string().min(1).optional(),
    participantId: z.string().uuid(),
    participantName: z.string().max(200).optional(),
    participantEmail: z.string().email().max(320).optional(),
    browserMetadata: browserMetadataSchema,
    eventTimeline: z.array(timelineEventSchema).min(1),
    dialSamples: z.array(dialSampleSchema),
    qualitySamples: z.array(qualitySampleSchema).default([]),
    traceRows: z.array(traceRowSchema).default([]),
    sessionQualitySummary: sessionQualitySummarySchema.optional(),
    annotations: z.array(annotationMarkerSchema).default([]),
    annotationSkipped: z.boolean().default(false),
    surveyResponses: z.array(surveyResponseSchema).min(1),
    frames: z.array(uploadFrameSchema),
    framePointers: z.array(framePointerSchema)
  })
  .superRefine((payload, ctx) => {
    if (payload.frames.length === 0 && payload.framePointers.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['frames'],
        message: 'Payload must include frames or frame pointers.'
      });
    }
  });

export type BrowserMetadata = z.infer<typeof browserMetadataSchema>;
export type TimelineEvent = z.infer<typeof timelineEventSchema>;
export type UploadFrame = z.infer<typeof uploadFrameSchema>;
export type FramePointer = z.infer<typeof framePointerSchema>;
export type DialSample = z.infer<typeof dialSampleSchema>;
export type QualitySample = z.infer<typeof qualitySampleSchema>;
export type TraceRow = z.infer<typeof traceRowSchema>;
export type SessionQualitySummary = z.infer<typeof sessionQualitySummarySchema>;
export type AnnotationMarker = z.infer<typeof annotationMarkerSchema>;
export type SurveyResponse = z.infer<typeof surveyResponseSchema>;
export type SessionUploadPayload = z.infer<typeof uploadPayloadSchema>;
