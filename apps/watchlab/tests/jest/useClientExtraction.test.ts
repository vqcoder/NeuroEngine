import { buildTraceRow } from '../../app/study/[studyId]/hooks/useClientExtraction';

function makeContext() {
  return {
    lastVideoTimeMs: 0,
    rollingFaceOk: [] as boolean[],
    rollingHeadPoseValid: [] as boolean[],
    rollingBlinks: [] as number[],
  };
}

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    videoTimeMs: 1000,
    timestampMs: Date.now(),
    face_ok: true,
    landmarks_ok: true,
    eye_openness: 0.8,
    blink: 0 as 0 | 1,
    au: { AU04: 0.1, AU06: 0.05, AU12: 0.2, AU25: 0.1, AU26: 0.05, AU45: 0.2 },
    au_norm: { AU04: 0.1, AU06: 0.05, AU12: 0.2, AU25: 0.1, AU26: 0.05, AU45: 0.2 },
    head_pose: { yaw: 5.0, pitch: -2.0, roll: 1.0 },
    pupil_dilation_proxy: 0.3,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// buildTraceRow
// ---------------------------------------------------------------------------

describe('buildTraceRow', () => {
  it('builds a valid TraceRow with face_ok=true', () => {
    const ctx = makeContext();
    const row = buildTraceRow(makeResult(), ctx);
    expect(row.face_ok).toBe(true);
    expect(row.landmarks_ok).toBe(true);
    expect(row.blink).toBe(0);
    expect(row.brightness).toBe(128);
    expect(row.quality_score).toBe(0.8);
    expect(row.tracking_confidence).toBe(0.75);
    expect(row.au).toHaveProperty('AU04');
  });

  it('builds a TraceRow with face_ok=false and landmarks_ok=false', () => {
    const ctx = makeContext();
    const row = buildTraceRow(
      makeResult({ face_ok: false, landmarks_ok: false, eye_openness: null }),
      ctx,
    );
    expect(row.face_ok).toBe(false);
    expect(row.landmarks_ok).toBe(false);
    expect(row.quality_score).toBe(0.2);
    expect(row.tracking_confidence).toBe(0.1);
  });

  it('accumulates traceRows across multiple calls', () => {
    const ctx = makeContext();
    const row1 = buildTraceRow(makeResult({ videoTimeMs: 1000 }), ctx);
    ctx.lastVideoTimeMs = 1000;
    const row2 = buildTraceRow(makeResult({ videoTimeMs: 1200 }), ctx);

    expect(row1.video_time_ms).toBe(1000);
    expect(row2.video_time_ms).toBe(1200);
    expect(ctx.rollingFaceOk).toHaveLength(2);
  });

  it('clamps blink_inhibition_score to [-1, 1]', () => {
    const ctx = makeContext();
    // Fill with all blinks to get extreme inhibition
    for (let i = 0; i < 300; i++) {
      ctx.rollingBlinks.push(1);
    }
    const row = buildTraceRow(makeResult({ blink: 1 }), ctx);
    expect(row.blink_inhibition_score).toBeGreaterThanOrEqual(-1);
    expect(row.blink_inhibition_score).toBeLessThanOrEqual(1);
  });

  it('clamps blink_inhibition_score to [-1, 1] when no blinks', () => {
    const ctx = makeContext();
    // Fill with no blinks
    for (let i = 0; i < 300; i++) {
      ctx.rollingBlinks.push(0);
    }
    const row = buildTraceRow(makeResult({ blink: 0 }), ctx);
    expect(row.blink_inhibition_score).toBeGreaterThanOrEqual(-1);
    expect(row.blink_inhibition_score).toBeLessThanOrEqual(1);
    // With 0 blinks and baseline 0.22, inhibition should be positive (suppressed)
    expect(row.blink_inhibition_score).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Hook state (structural tests — no Worker mock needed)
// ---------------------------------------------------------------------------

describe('useClientExtraction module', () => {
  it('exports buildTraceRow as a testable helper', () => {
    expect(typeof buildTraceRow).toBe('function');
  });

  it('exports useClientExtraction hook', () => {
    const mod = jest.requireActual(
      '../../app/study/[studyId]/hooks/useClientExtraction'
    ) as Record<string, unknown>;
    expect(typeof mod.useClientExtraction).toBe('function');
  });
});
