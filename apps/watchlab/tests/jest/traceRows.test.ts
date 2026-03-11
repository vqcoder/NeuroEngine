import { resolveTraceRowsForUpload } from '@/lib/traceRows';

const stddev = (values: number[]): number => {
  const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
  const variance = values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
};

describe('resolveTraceRowsForUpload', () => {
  test('uses provided trace rows when present', () => {
    const result = resolveTraceRowsForUpload({
      traceRows: [
        {
          video_time_ms: 2000,
          t_ms: 2000,
          face_ok: true,
          brightness: 72,
          landmarks_ok: true,
          blink: 0,
          au: { AU12: 0.2 },
          au_norm: { AU12: 0.2 },
          head_pose: { yaw: 0, pitch: 0, roll: 0 },
          quality_flags: []
        },
        {
          video_time_ms: 1000,
          t_ms: 1000,
          face_ok: true,
          brightness: 70,
          landmarks_ok: true,
          blink: 1,
          au: { AU12: 0.1 },
          au_norm: { AU12: 0.1 },
          head_pose: { yaw: 0, pitch: 0, roll: 0 },
          quality_flags: []
        }
      ],
      dialSamples: [],
      eventTimeline: [{ videoTimeMs: 2000 }],
      qualitySamples: []
    });

    expect(result.traceSource).toBe('provided');
    expect(result.traceRows).toHaveLength(2);
    expect(result.traceRows[0].video_time_ms).toBe(1000);
    expect(result.traceRows[1].video_time_ms).toBe(2000);
  });

  test('falls back to synthetic trace rows when no trace rows are provided', () => {
    const result = resolveTraceRowsForUpload({
      traceRows: [],
      dialSamples: [{ videoTimeMs: 1000, value: 52 }],
      eventTimeline: [{ videoTimeMs: 1000 }, { videoTimeMs: 2200 }],
      qualitySamples: [],
      allowSyntheticFallback: true
    });

    expect(result.traceSource).toBe('synthetic_fallback');
    expect(result.traceRows.length).toBeGreaterThan(0);
    expect(result.traceRows[0]).toHaveProperty('video_time_ms');
    expect(result.traceRows[0]).toHaveProperty('reward_proxy');
  });

  test('throws when trace rows are missing and synthetic fallback is disabled', () => {
    expect(() =>
      resolveTraceRowsForUpload({
        traceRows: [],
        dialSamples: [{ videoTimeMs: 1000, value: 52 }],
        eventTimeline: [{ videoTimeMs: 1000 }, { videoTimeMs: 2200 }],
        qualitySamples: [],
        allowSyntheticFallback: false
      })
    ).toThrow('Upload requires canonical traceRows aligned to video_time_ms');
  });

  // T8a: intra-session variance — flat output means the scoring pipeline is broken
  test('T8a: synthetic fallback rows have non-trivial reward_proxy variance', () => {
    // Build a 60-second session with varying dial values to generate signal diversity
    const dialSamples = Array.from({ length: 61 }, (_, i) => ({
      videoTimeMs: i * 1000,
      value: 30 + Math.round(40 * Math.sin((i / 60) * Math.PI * 4))
    }));
    const eventTimeline = [{ videoTimeMs: 0 }, { videoTimeMs: 60000 }];

    const result = resolveTraceRowsForUpload({
      traceRows: [],
      dialSamples,
      eventTimeline,
      qualitySamples: [],
      allowSyntheticFallback: true
    });

    expect(result.traceRows.length).toBeGreaterThanOrEqual(30);

    const rewardProxies = result.traceRows
      .map((row) => row.reward_proxy)
      .filter((v): v is number => typeof v === 'number');

    expect(rewardProxies.length).toBeGreaterThan(0);
    const sd = stddev(rewardProxies);
    // stddev should be > 1.0 for a session with meaningful signal variation
    expect(sd).toBeGreaterThan(1.0);
  });

  test('T8a: provided trace rows with real variance pass the stddev threshold', () => {
    const traceRows: Array<{
      video_time_ms: number; t_ms: number; face_ok: boolean; brightness: number;
      landmarks_ok: boolean; blink: 0 | 1; au: Record<string, number>;
      au_norm: Record<string, number>; head_pose: { yaw: number; pitch: number; roll: number };
      quality_flags: string[];
    }> = Array.from({ length: 30 }, (_, i) => ({
      video_time_ms: i * 1000,
      t_ms: i * 1000,
      face_ok: true,
      brightness: 60 + Math.round(20 * Math.sin(i)),
      landmarks_ok: true,
      blink: (i % 5 === 0 ? 1 : 0) as 0 | 1,
      au: { AU12: 0.1 + 0.3 * Math.abs(Math.sin(i / 3)) },
      au_norm: { AU12: 0.1 + 0.3 * Math.abs(Math.sin(i / 3)) },
      head_pose: { yaw: i * 0.5, pitch: 0, roll: 0 },
      quality_flags: []
    }));

    const result = resolveTraceRowsForUpload({
      traceRows,
      dialSamples: [],
      eventTimeline: [{ videoTimeMs: 29000 }],
      qualitySamples: []
    });

    expect(result.traceSource).toBe('provided');
    const brightnessValues = result.traceRows.map((row) => row.brightness as number);
    const sd = stddev(brightnessValues);
    expect(sd).toBeGreaterThan(1.0);
  });
});
