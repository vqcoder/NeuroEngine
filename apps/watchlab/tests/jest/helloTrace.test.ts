import { buildFallbackDialSamples, buildPlaceholderTraceRows } from '@/lib/helloTrace';

describe('hello trace placeholder generation', () => {
  test('builds fallback dial samples from timeline span', () => {
    const samples = buildFallbackDialSamples([
      { videoTimeMs: 0 },
      { videoTimeMs: 6200 }
    ]);

    expect(samples.length).toBeGreaterThanOrEqual(6);
    expect(samples[0].videoTimeMs).toBe(0);
    expect(samples[samples.length - 1].videoTimeMs).toBeGreaterThanOrEqual(6000);
  });

  test('emits trace rows with expected AU/blink fields', () => {
    const rows = buildPlaceholderTraceRows(
      [
        { videoTimeMs: 0, value: 50 },
        { videoTimeMs: 1000, value: 65 },
        { videoTimeMs: 2000, value: 35 }
      ],
      [{ videoTimeMs: 2000 }]
    );

    expect(rows.length).toBeGreaterThanOrEqual(3);
    expect(rows[0].t_ms).toBe(0);
    expect(rows.some((row) => row.video_time_ms === 1000)).toBe(true);
    expect(rows.some((row) => row.video_time_ms === 2000)).toBe(true);
    expect(rows[0]).toMatchObject({
      t_ms: 0,
      face_ok: true,
      landmarks_ok: true
    });
    expect(typeof rows[1].au.AU12).toBe('number');
    expect(typeof rows[1].au_norm.AU04).toBe('number');
    rows.forEach((row) => {
      expect(row.blink === 0 || row.blink === 1).toBe(true);
      expect(row.dial).toBeGreaterThanOrEqual(0);
      expect(row.dial).toBeLessThanOrEqual(100);
      expect(row.tracking_confidence).toBeGreaterThanOrEqual(0);
      expect(row.tracking_confidence).toBeLessThanOrEqual(1);
    });
  });

  // T2: golden output — t_ms must always equal video_time_ms for backward compat
  test('T2 golden: t_ms equals video_time_ms on every row', () => {
    const rows = buildPlaceholderTraceRows(
      [{ videoTimeMs: 0, value: 50 }, { videoTimeMs: 3000, value: 80 }, { videoTimeMs: 6000, value: 30 }],
      [{ videoTimeMs: 6000 }]
    );
    rows.forEach((row) => {
      expect(row.t_ms).toBe(row.video_time_ms);
    });
  });

  // T2: golden output — AU values must stay in a bounded range (synthetic rows may have small negative offsets from interpolation)
  test('T2 golden: all AU values are in bounded range [-0.1, 1.1]', () => {
    const rows = buildPlaceholderTraceRows(
      [{ videoTimeMs: 0, value: 0 }, { videoTimeMs: 1000, value: 100 }, { videoTimeMs: 2000, value: 50 }],
      [{ videoTimeMs: 2000 }]
    );
    rows.forEach((row) => {
      for (const val of Object.values(row.au)) {
        expect(val).toBeGreaterThanOrEqual(-0.1);
        expect(val).toBeLessThanOrEqual(1.1);
      }
      for (const val of Object.values(row.au_norm)) {
        expect(val).toBeGreaterThanOrEqual(-0.1);
        expect(val).toBeLessThanOrEqual(1.1);
      }
    });
  });

  // T2: golden output — reward_proxy is present and in expected range for provided dial
  test('T2 golden: reward_proxy present and bounded when dial samples provided', () => {
    const rows = buildPlaceholderTraceRows(
      [{ videoTimeMs: 0, value: 50 }, { videoTimeMs: 5000, value: 75 }],
      [{ videoTimeMs: 5000 }]
    );
    rows.forEach((row) => {
      if (row.reward_proxy !== undefined) {
        expect(row.reward_proxy).toBeGreaterThanOrEqual(0);
        expect(row.reward_proxy).toBeLessThanOrEqual(100);
      }
    });
    const withReward = rows.filter((r) => r.reward_proxy !== undefined);
    expect(withReward.length).toBeGreaterThan(0);
  });

  // T2: exact numerical golden-output — pins the reward_proxy formula so any silent drift fails the build.
  // At t=0ms the trigonometric terms resolve to constants: sin(0)=0, cos(0)=1.
  // Expected values derived from formula:
  //   rewardProxy = clamp(30 + dial×0.45 + au12×28 + au6×16 − au4×12 + blinkInhibitionScore×9, 0, 100)
  // where at t=0ms:
  //   blink=0, rollingBlinkRate=0.18, blinkInhibitionScore=(0.22-0.18)/0.22 ≈ 0.181818
  //   au12 = 0.07 + dialNorm×0.09, au6 = 0.065 + dialNorm×0.05, au4 = 0.03 + max(0,−dialNorm)×0.09
  test('T2 golden exact: reward_proxy at t=0ms matches formula for dial=50', () => {
    const rows = buildPlaceholderTraceRows(
      [{ videoTimeMs: 0, value: 50 }],
      [{ videoTimeMs: 0 }]
    );
    const row = rows.find((r) => r.video_time_ms === 0);
    expect(row).toBeDefined();
    // dial=50 → dialNorm=0 → reward_proxy = clamp(30+22.5+1.96+1.04−0.36+1.636362, 0,100) = 56.776362
    expect(row!.reward_proxy).toBeCloseTo(56.776362, 3);
  });

  test('T2 golden exact: reward_proxy at t=0ms for dial=0 is lower than dial=50', () => {
    const rows0 = buildPlaceholderTraceRows([{ videoTimeMs: 0, value: 0 }], [{ videoTimeMs: 0 }]);
    const rows50 = buildPlaceholderTraceRows([{ videoTimeMs: 0, value: 50 }], [{ videoTimeMs: 0 }]);
    const rp0 = rows0.find((r) => r.video_time_ms === 0)!.reward_proxy;
    const rp50 = rows50.find((r) => r.video_time_ms === 0)!.reward_proxy;
    // dial=0 → reward_proxy ≈ 29.876; dial=50 → reward_proxy ≈ 56.776
    expect(rp0).toBeCloseTo(29.876, 2);
    expect(rp0!).toBeLessThan(rp50!);
  });

  test('T2 golden exact: reward_proxy at t=0ms for dial=100 is higher than dial=50', () => {
    const rows100 = buildPlaceholderTraceRows([{ videoTimeMs: 0, value: 100 }], [{ videoTimeMs: 0 }]);
    const rows50 = buildPlaceholderTraceRows([{ videoTimeMs: 0, value: 50 }], [{ videoTimeMs: 0 }]);
    const rp100 = rows100.find((r) => r.video_time_ms === 0)!.reward_proxy;
    const rp50 = rows50.find((r) => r.video_time_ms === 0)!.reward_proxy;
    // dial=100 → reward_proxy ≈ 82.596
    expect(rp100).toBeCloseTo(82.596, 2);
    expect(rp100!).toBeGreaterThan(rp50!);
  });

  test('T2 golden exact: all signal fields have correct types on every row', () => {
    const rows = buildPlaceholderTraceRows(
      [{ videoTimeMs: 0, value: 50 }, { videoTimeMs: 2000, value: 70 }],
      [{ videoTimeMs: 2000 }]
    );
    rows.forEach((row) => {
      expect(typeof row.t_ms).toBe('number');
      expect(typeof row.video_time_ms).toBe('number');
      expect(typeof row.dial).toBe('number');
      expect(typeof row.reward_proxy).toBe('number');
      expect(typeof row.blink).toBe('number');
      expect(typeof row.rolling_blink_rate).toBe('number');
      expect(typeof row.blink_inhibition_score).toBe('number');
      expect(typeof row.tracking_confidence).toBe('number');
      expect(row.blink === 0 || row.blink === 1).toBe(true);
      expect(row.reward_proxy).toBeGreaterThanOrEqual(0);
      expect(row.reward_proxy).toBeLessThanOrEqual(100);
      expect(row.tracking_confidence).toBeGreaterThanOrEqual(0);
      expect(row.tracking_confidence).toBeLessThanOrEqual(1);
    });
  });
});
