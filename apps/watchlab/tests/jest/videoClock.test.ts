import { VideoTimeTracker, isMonotonic, nextVideoTimeMs } from '@/lib/videoClock';

describe('video clock behavior', () => {
  test('videoTimeMs stays monotonic during playback updates', () => {
    let value = 0;
    const samples = [10, 33, 66, 99, 132, 165, 198, 197, 230];
    const output: number[] = [];

    samples.forEach((sample) => {
      value = nextVideoTimeMs(value, sample, false);
      output.push(value);
    });

    expect(isMonotonic(output)).toBe(true);
    expect(output[output.length - 1]).toBe(230);
  });

  test('seek updates can move time backward when explicitly allowed', () => {
    const value = nextVideoTimeMs(8000, 1200, true);
    expect(value).toBe(1200);
  });

  test('tracker remains monotonic during uninterrupted playback', () => {
    const tracker = new VideoTimeTracker();
    const output: number[] = [];

    for (let step = 0; step < 8; step += 1) {
      output.push(
        tracker.sample({
          measuredVideoTimeMs: step * 250,
          clientMonotonicMs: step * 250,
          isPlaying: true,
          playbackRate: 1,
          isBuffering: false
        })
      );
    }

    expect(isMonotonic(output)).toBe(true);
    expect(output[output.length - 1]).toBeGreaterThan(output[0]);
  });

  test('tracker preserves accurate time after seek and resumes from new position', () => {
    const tracker = new VideoTimeTracker();

    tracker.sample({
      measuredVideoTimeMs: 3000,
      clientMonotonicMs: 3000,
      isPlaying: true,
      playbackRate: 1,
      isBuffering: false
    });

    const seekTime = tracker.seek(1200, 3200);
    expect(seekTime).toBe(1200);

    const afterSeek = tracker.sample({
      measuredVideoTimeMs: 1450,
      clientMonotonicMs: 3450,
      isPlaying: true,
      playbackRate: 1,
      isBuffering: false
    });
    expect(afterSeek).toBeGreaterThanOrEqual(1450);
    expect(afterSeek).toBeLessThan(1700);
  });

  test('tracker honors rate changes and stalls while buffering', () => {
    const tracker = new VideoTimeTracker();

    const base = tracker.sample({
      measuredVideoTimeMs: 1000,
      clientMonotonicMs: 1000,
      isPlaying: true,
      playbackRate: 1,
      isBuffering: false
    });
    expect(base).toBe(1000);

    const doubleRate = tracker.sample({
      measuredVideoTimeMs: 1900,
      clientMonotonicMs: 1400,
      isPlaying: true,
      playbackRate: 2,
      isBuffering: false
    });
    expect(doubleRate).toBeGreaterThanOrEqual(1800);

    const buffering = tracker.sample({
      measuredVideoTimeMs: 1900,
      clientMonotonicMs: 1800,
      isPlaying: true,
      playbackRate: 2,
      isBuffering: true
    });
    expect(buffering).toBe(doubleRate);
  });
});
