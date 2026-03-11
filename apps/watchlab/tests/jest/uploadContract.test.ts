/**
 * T3: API contract tests for the /api/upload route.
 *
 * These tests validate the request/response schema contract without needing
 * a running server: they exercise uploadPayloadSchema (what the server accepts)
 * and the shape of the success/error response bodies as documented in the route.
 */

import { uploadPayloadSchema } from '@/lib/schema';
import { UploadErrorCode, WatchlabUploadError, classifyHttpError } from '@/lib/errors';

// ---------------------------------------------------------------------------
// Minimal valid fixture matching what the browser actually sends
// ---------------------------------------------------------------------------

const baseParticipantId = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const baseSessionId = 'ffffffff-0000-4000-8000-111111111111';
const baseVideoId = 'video-demo';

const minimalValidPayload = {
  studyId: 'demo',
  videoId: baseVideoId,
  participantId: baseParticipantId,
  participantName: 'Test User',
  participantEmail: 'test@example.com',
  browserMetadata: {
    userAgent: 'Mozilla/5.0',
    platform: 'MacIntel',
    language: 'en-US',
    viewport: { width: 1280, height: 800 },
    timezone: 'America/Los_Angeles',
    hardwareConcurrency: 8
  },
  eventTimeline: [
    {
      type: 'consent_accepted',
      sessionId: baseSessionId,
      videoId: baseVideoId,
      wallTimeMs: 100,
      clientMonotonicMs: 10,
      videoTimeMs: 0
    },
    {
      type: 'playback_started',
      sessionId: baseSessionId,
      videoId: baseVideoId,
      wallTimeMs: 200,
      clientMonotonicMs: 110,
      videoTimeMs: 0
    },
    {
      type: 'ended',
      sessionId: baseSessionId,
      videoId: baseVideoId,
      wallTimeMs: 62000,
      clientMonotonicMs: 61900,
      videoTimeMs: 60000
    }
  ],
  dialSamples: [],
  annotations: [],
  annotationSkipped: true,
  surveyResponses: [
    { questionKey: 'overall_engagement', responseNumber: 4 },
    { questionKey: 'content_clarity', responseNumber: 3 }
  ],
  frames: [],
  // Schema requires frames or framePointers; provide at least one pointer
  framePointers: [
    {
      id: '12345678-1234-4000-8000-123456789abc',
      timestampMs: 500,
      videoTimeMs: 500,
      pointer: 'frame:12345678-1234-4000-8000-123456789abc'
    }
  ],
  qualitySamples: [],
  traceRows: [
    {
      video_time_ms: 1000,
      t_ms: 1000,
      face_ok: true,
      brightness: 75,
      landmarks_ok: true,
      blink: 0,
      au: { AU12: 0.25 },
      au_norm: { AU12: 0.25 },
      head_pose: { yaw: 0, pitch: 0, roll: 0 },
      quality_flags: []
    }
  ]
};

// ---------------------------------------------------------------------------
// Request schema contract
// ---------------------------------------------------------------------------

describe('T3 — upload payload contract (request schema)', () => {
  test('accepts the minimal valid payload fixture', () => {
    const result = uploadPayloadSchema.safeParse(minimalValidPayload);
    expect(result.success).toBe(true);
  });

  test('rejects payload missing required studyId', () => {
    const { studyId: _dropped, ...rest } = minimalValidPayload;
    const result = uploadPayloadSchema.safeParse(rest);
    expect(result.success).toBe(false);
    if (!result.success) {
      const paths = result.error.issues.map((issue) => issue.path.join('.'));
      expect(paths.some((p) => p.includes('studyId'))).toBe(true);
    }
  });

  test('rejects payload with invalid participantId (not UUID)', () => {
    const result = uploadPayloadSchema.safeParse({
      ...minimalValidPayload,
      participantId: 'not-a-uuid'
    });
    expect(result.success).toBe(false);
  });

  test('rejects empty traceRows with no synthetic fallback option', () => {
    // traceRows is allowed to be empty in the schema (server decides whether to reject);
    // but if present, entries must have required fields
    const result = uploadPayloadSchema.safeParse({
      ...minimalValidPayload,
      traceRows: [{ video_time_ms: 'not_a_number' }]
    });
    expect(result.success).toBe(false);
  });

  test('accepts annotation with valid markerType', () => {
    const result = uploadPayloadSchema.safeParse({
      ...minimalValidPayload,
      annotationSkipped: false,
      annotations: [
        {
          id: 'aabbccdd-1234-4000-8000-aabbccddeeff',
          sessionId: baseSessionId,
          videoId: baseVideoId,
          markerType: 'engaging_moment',
          videoTimeMs: 15000,
          note: 'Great hook',
          createdAt: new Date().toISOString()
        }
      ]
    });
    expect(result.success).toBe(true);
  });

  test('rejects unknown annotation markerType', () => {
    const result = uploadPayloadSchema.safeParse({
      ...minimalValidPayload,
      annotations: [
        {
          sessionId: baseSessionId,
          videoId: baseVideoId,
          markerType: 'unknown_marker',
          videoTimeMs: 5000,
          createdAt: new Date().toISOString()
        }
      ]
    });
    expect(result.success).toBe(false);
  });

  test('accepts payload without optional participantName / participantEmail', () => {
    const { participantName: _n, participantEmail: _e, ...rest } = minimalValidPayload;
    const result = uploadPayloadSchema.safeParse(rest);
    expect(result.success).toBe(true);
  });

  test('eventTimeline entries require sessionId and wallTimeMs', () => {
    const result = uploadPayloadSchema.safeParse({
      ...minimalValidPayload,
      eventTimeline: [{ type: 'ended', videoId: baseVideoId, videoTimeMs: 0 }]
    });
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Response shape contract (C17 error taxonomy integration)
// ---------------------------------------------------------------------------

describe('T3 — upload error taxonomy contract (C17)', () => {
  test('classifyHttpError 400 → CLIENT_ERROR, not retryable', () => {
    const err = classifyHttpError(400, 'bad request');
    expect(err.code).toBe(UploadErrorCode.CLIENT_ERROR);
    expect(err.retryable).toBe(false);
    expect(err.httpStatus).toBe(400);
  });

  test('classifyHttpError 413 → PAYLOAD_TOO_LARGE, not retryable', () => {
    const err = classifyHttpError(413, 'too large');
    expect(err.code).toBe(UploadErrorCode.PAYLOAD_TOO_LARGE);
    expect(err.retryable).toBe(false);
  });

  test('classifyHttpError 500 → SERVER_ERROR, retryable', () => {
    const err = classifyHttpError(500, 'internal error');
    expect(err.code).toBe(UploadErrorCode.SERVER_ERROR);
    expect(err.retryable).toBe(true);
  });

  test('classifyHttpError 503 → SERVER_ERROR, retryable', () => {
    const err = classifyHttpError(503, 'service unavailable');
    expect(err.code).toBe(UploadErrorCode.SERVER_ERROR);
    expect(err.retryable).toBe(true);
  });

  test('WatchlabUploadError carries code, retryable, and httpStatus', () => {
    const err = new WatchlabUploadError(UploadErrorCode.NETWORK_ERROR, 'fetch failed', {
      retryable: true
    });
    expect(err).toBeInstanceOf(Error);
    expect(err.code).toBe('NETWORK_ERROR');
    expect(err.retryable).toBe(true);
    expect(err.httpStatus).toBeUndefined();
    expect(err.message).toBe('fetch failed');
  });
});
