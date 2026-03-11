import { uploadPayloadSchema } from '@/lib/schema';

describe('uploadPayloadSchema', () => {
  test('accepts a valid payload', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      sourceUrl: '/api/video-assets/kalshi-1.mp4',
      participantId: '81fb7fe4-3d69-4f8f-ad88-f8fd0f8a4372',
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
          sessionId: 'a8e7d09e-af6d-4a03-825d-7d099525f580',
          videoId: 'video-demo',
          wallTimeMs: 100,
          clientMonotonicMs: 10,
          videoTimeMs: 0
        }
      ],
      dialSamples: [
        {
          id: '32ff5f8a-cb21-4f38-a40e-08208d3f1f01',
          wallTimeMs: 1000,
          videoTimeMs: 500,
          value: 64
        }
      ],
      traceRows: [
        {
          t_ms: 500,
          face_ok: true,
          brightness: 70,
          landmarks_ok: true,
          blink: 0,
          au: { AU12: 0.2 },
          au_norm: { AU12: 0.2 },
          head_pose: { yaw: 0, pitch: 0, roll: 0 },
          quality_flags: []
        }
      ],
      annotations: [
        {
          id: '4aa458e8-5268-4253-9b0d-c56cfa98f6c4',
          sessionId: 'a8e7d09e-af6d-4a03-825d-7d099525f580',
          videoId: 'video-demo',
          markerType: 'engaging_moment',
          videoTimeMs: 1200,
          note: 'Strong hook',
          createdAt: '2026-03-05T10:00:00.000Z'
        }
      ],
      annotationSkipped: false,
      surveyResponses: [
        {
          questionKey: 'overall_interest_likert',
          responseNumber: 4
        },
        {
          questionKey: 'post_video_feedback_text',
          responseText: 'Good pacing overall.'
        }
      ],
      frames: [
        {
          id: 'eb73ff0c-b9ad-4011-9d4b-2f89b71083e4',
          timestampMs: 200,
          jpegBase64: 'YmFzZTY0LWZyYW1lLWRhdGE='
        }
      ],
      framePointers: []
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
    if (!result.success) {
      return;
    }
    expect(result.data.sourceUrl).toBe('/api/video-assets/kalshi-1.mp4');
  });

  test('normalizes trace rows so both t_ms and video_time_ms are populated', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      participantId: '81fb7fe4-3d69-4f8f-ad88-f8fd0f8a4372',
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
          sessionId: 'a8e7d09e-af6d-4a03-825d-7d099525f580',
          videoId: 'video-demo',
          wallTimeMs: 100,
          clientMonotonicMs: 10,
          videoTimeMs: 0
        }
      ],
      dialSamples: [],
      traceRows: [
        {
          t_ms: 1500,
          face_ok: true,
          brightness: 66,
          landmarks_ok: true,
          blink: 0,
          au: { AU12: 0.11 },
          au_norm: { AU12: 0.11 },
          head_pose: { yaw: 0, pitch: 0, roll: 0 },
          quality_flags: []
        }
      ],
      annotations: [],
      annotationSkipped: true,
      surveyResponses: [
        {
          questionKey: 'overall_interest_likert',
          responseNumber: 3
        }
      ],
      frames: [
        {
          id: 'eb73ff0c-b9ad-4011-9d4b-2f89b71083e4',
          timestampMs: 200,
          jpegBase64: 'YmFzZTY0LWZyYW1lLWRhdGE='
        }
      ],
      framePointers: []
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(true);
    if (!result.success) {
      return;
    }
    expect(result.data.traceRows[0].t_ms).toBe(1500);
    expect(result.data.traceRows[0].video_time_ms).toBe(1500);
  });

  test('rejects when no frames and no pointers are provided', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      participantId: '93d7f08c-34e5-46fc-825c-44c9f2a95f8d',
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
          sessionId: 'f6f08b4c-2e58-4ccf-b0d8-55f54225ca1f',
          videoId: 'video-demo',
          wallTimeMs: 100,
          clientMonotonicMs: 10,
          videoTimeMs: 0
        }
      ],
      dialSamples: [],
      annotations: [],
      annotationSkipped: true,
      surveyResponses: [
        {
          questionKey: 'overall_interest_likert',
          responseNumber: 3
        }
      ],
      frames: [],
      framePointers: []
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  test('rejects timeline events that omit required telemetry keys', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      participantId: 'f6b649ad-f5a0-46df-9706-670dd9ba596a',
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
          type: 'play',
          wallTimeMs: 1000,
          videoTimeMs: 2500
        }
      ],
      dialSamples: [],
      annotations: [],
      annotationSkipped: true,
      surveyResponses: [
        {
          questionKey: 'session_completion_status',
          responseJson: { status: 'incomplete' }
        }
      ],
      frames: [],
      framePointers: [
        {
          id: '8fb0f649-2cc6-4cde-8718-26ccf196b566',
          timestampMs: 300,
          pointer: 'frame-1'
        }
      ]
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  test('rejects annotation markers with unknown marker type', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      participantId: 'f6b649ad-f5a0-46df-9706-670dd9ba596a',
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
          type: 'play',
          sessionId: 'f6f08b4c-2e58-4ccf-b0d8-55f54225ca1f',
          videoId: 'video-demo',
          wallTimeMs: 1000,
          clientMonotonicMs: 7,
          videoTimeMs: 2500
        }
      ],
      dialSamples: [],
      annotations: [
        {
          id: '4aa458e8-5268-4253-9b0d-c56cfa98f6c4',
          sessionId: 'f6f08b4c-2e58-4ccf-b0d8-55f54225ca1f',
          videoId: 'video-demo',
          markerType: 'unknown_type',
          videoTimeMs: 1200,
          note: null,
          createdAt: '2026-03-05T10:00:00.000Z'
        }
      ],
      annotationSkipped: false,
      surveyResponses: [
        {
          questionKey: 'session_completion_status',
          responseJson: { status: 'complete' }
        }
      ],
      frames: [],
      framePointers: [
        {
          id: '8fb0f649-2cc6-4cde-8718-26ccf196b566',
          timestampMs: 300,
          pointer: 'frame-1'
        }
      ]
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });

  test('rejects legacy in-play tapping event types in timeline schema', () => {
    const payload = {
      studyId: 'demo',
      videoId: 'video-demo',
      participantId: 'f6b649ad-f5a0-46df-9706-670dd9ba596a',
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
          type: 'reaction_tap',
          sessionId: 'f6f08b4c-2e58-4ccf-b0d8-55f54225ca1f',
          videoId: 'video-demo',
          wallTimeMs: 1000,
          clientMonotonicMs: 7,
          videoTimeMs: 2500
        }
      ],
      dialSamples: [],
      annotations: [],
      annotationSkipped: true,
      surveyResponses: [
        {
          questionKey: 'session_completion_status',
          responseJson: { status: 'complete' }
        }
      ],
      frames: [],
      framePointers: [
        {
          id: '8fb0f649-2cc6-4cde-8718-26ccf196b566',
          timestampMs: 300,
          pointer: 'frame-1'
        }
      ]
    };

    const result = uploadPayloadSchema.safeParse(payload);
    expect(result.success).toBe(false);
  });
});
