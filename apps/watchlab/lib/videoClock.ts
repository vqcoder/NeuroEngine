export const nextVideoTimeMs = (
  previousMs: number,
  measuredMs: number,
  allowBackward: boolean
): number => {
  if (allowBackward) {
    return measuredMs;
  }
  return measuredMs >= previousMs ? measuredMs : previousMs;
};

export const isMonotonic = (values: number[]): boolean => {
  for (let i = 1; i < values.length; i += 1) {
    if (values[i] < values[i - 1]) {
      return false;
    }
  }
  return true;
};

export type VideoTimeTrackerSample = {
  measuredVideoTimeMs: number;
  clientMonotonicMs: number;
  allowBackward?: boolean;
  isPlaying?: boolean;
  playbackRate?: number;
  isBuffering?: boolean;
};

const clampNonNegativeInt = (value: number): number => {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.round(value));
};

/**
 * Tracks a canonical video-time clock across playback, pause, seek, buffering,
 * and tab lifecycle events while still allowing explicit backward seeks.
 */
export class VideoTimeTracker {
  private syncedVideoTimeMs = 0;
  private lastClientMonotonicMs = 0;
  private isPlaying = false;
  private playbackRate = 1;
  private isBuffering = false;

  public getVideoTimeMs() {
    return this.syncedVideoTimeMs;
  }

  public setPlaybackState(input: {
    isPlaying?: boolean;
    playbackRate?: number;
    isBuffering?: boolean;
  }) {
    if (typeof input.isPlaying === 'boolean') {
      this.isPlaying = input.isPlaying;
    }
    if (typeof input.playbackRate === 'number' && Number.isFinite(input.playbackRate)) {
      this.playbackRate = input.playbackRate;
    }
    if (typeof input.isBuffering === 'boolean') {
      this.isBuffering = input.isBuffering;
    }
  }

  public sample(input: VideoTimeTrackerSample): number {
    const measuredVideoTimeMs = clampNonNegativeInt(input.measuredVideoTimeMs);
    const clientMonotonicMs = clampNonNegativeInt(input.clientMonotonicMs);
    const allowBackward = Boolean(input.allowBackward);

    this.setPlaybackState({
      isPlaying: input.isPlaying,
      playbackRate: input.playbackRate,
      isBuffering: input.isBuffering
    });

    const elapsedMs =
      this.lastClientMonotonicMs > 0
        ? Math.max(0, clientMonotonicMs - this.lastClientMonotonicMs)
        : 0;

    const projectedMs =
      this.isPlaying && !this.isBuffering
        ? this.syncedVideoTimeMs + elapsedMs * Math.max(0, this.playbackRate)
        : this.syncedVideoTimeMs;

    const driftToleranceMs = 120;
    const stabilizedMeasuredMs =
      this.isPlaying && !this.isBuffering
        ? Math.max(measuredVideoTimeMs, clampNonNegativeInt(projectedMs - driftToleranceMs))
        : measuredVideoTimeMs;

    this.syncedVideoTimeMs = allowBackward
      ? measuredVideoTimeMs
      : Math.max(this.syncedVideoTimeMs, stabilizedMeasuredMs);
    this.lastClientMonotonicMs = clientMonotonicMs;

    return this.syncedVideoTimeMs;
  }

  public seek(measuredVideoTimeMs: number, clientMonotonicMs: number): number {
    return this.sample({
      measuredVideoTimeMs,
      clientMonotonicMs,
      allowBackward: true
    });
  }
}
