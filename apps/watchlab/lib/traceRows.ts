import { buildPlaceholderTraceRows, type PlaceholderTraceRow } from '@/lib/helloTrace';
import type { DialSample, QualitySample, TimelineEvent, TraceRow } from '@/lib/schema';
import {
  clampNumber,
  defaultTraceAu,
  QUALITY_SAMPLE_WINDOW_MS,
  TRACE_DEFAULT_BLINK_BASELINE_RATE
} from '@/lib/studyTypes';

type ResolveTraceRowsInput = {
  traceRows: TraceRow[];
  dialSamples: Array<{ videoTimeMs: number; value: number }>;
  eventTimeline: Array<{ videoTimeMs: number }>;
  qualitySamples: Array<{
    videoTimeMs: number;
    brightness: number;
    blur: number;
    fps: number;
    fpsStability: number;
    faceDetected: boolean;
    faceVisiblePct: number;
    headPoseValidPct: number;
    occlusionScore: number;
    qualityScore: number;
    trackingConfidence: number;
    qualityFlags: Array<'low_light' | 'blur' | 'face_lost' | 'high_yaw_pitch'>;
  }>;
  allowSyntheticFallback?: boolean;
};

type ResolveTraceRowsResult = {
  traceRows: PlaceholderTraceRow[];
  traceSource: 'provided' | 'synthetic_fallback';
};

export class MissingCanonicalTraceRowsError extends Error {
  constructor() {
    super(
      'Upload requires canonical traceRows aligned to video_time_ms. Synthetic fallback is disabled for this study.'
    );
    this.name = 'MissingCanonicalTraceRowsError';
  }
}

const normalizeProvidedTraceRows = (rows: TraceRow[]): PlaceholderTraceRow[] => {
  return rows
    .map((row) => ({
      ...(row as PlaceholderTraceRow),
      video_time_ms: Math.max(0, Math.round(row.video_time_ms)),
      t_ms: Math.max(0, Math.round(row.t_ms))
    }))
    .sort((left, right) => left.video_time_ms - right.video_time_ms);
};

export const resolveTraceRowsForUpload = (
  input: ResolveTraceRowsInput
): ResolveTraceRowsResult => {
  if (input.traceRows.length > 0) {
    return {
      traceRows: normalizeProvidedTraceRows(input.traceRows),
      traceSource: 'provided'
    };
  }

  if (!input.allowSyntheticFallback) {
    throw new MissingCanonicalTraceRowsError();
  }

  return {
    traceRows: buildPlaceholderTraceRows(input.dialSamples, input.eventTimeline, input.qualitySamples),
    traceSource: 'synthetic_fallback'
  };
};

// ---------------------------------------------------------------------------
// buildCanonicalTraceRows — extracted from study-client.tsx (A21)
// Pure computation that transforms dial samples, quality samples, and
// timeline events into the canonical TraceRow[] format for upload.
// ---------------------------------------------------------------------------

export type BuildCanonicalTraceRowsInput = {
  dialSamples: DialSample[];
  qualitySamples: QualitySample[];
  timeline: TimelineEvent[];
  annotationDurationMs: number;
};

export const buildCanonicalTraceRows = (input: BuildCanonicalTraceRowsInput): TraceRow[] => {
  const { dialSamples, qualitySamples: rawQualitySamples, timeline, annotationDurationMs } = input;

  const orderedDialSamples = [...dialSamples]
    .filter(
      (sample) =>
        Number.isFinite(sample.videoTimeMs) &&
        sample.videoTimeMs >= 0 &&
        Number.isFinite(sample.value)
    )
    .sort((left, right) => left.videoTimeMs - right.videoTimeMs);

  let dialIndex = 0;
  const dialValueAt = (videoTimeMs: number): number | undefined => {
    while (
      dialIndex + 1 < orderedDialSamples.length &&
      orderedDialSamples[dialIndex + 1].videoTimeMs <= videoTimeMs
    ) {
      dialIndex += 1;
    }
    const dialSample = orderedDialSamples[dialIndex];
    if (!dialSample || dialSample.videoTimeMs > videoTimeMs) {
      return undefined;
    }
    return Number(Math.max(0, Math.min(100, dialSample.value)).toFixed(2));
  };

  const qualitySamples = [...rawQualitySamples]
    .filter((sample) => Number.isFinite(sample.videoTimeMs) && sample.videoTimeMs >= 0)
    .sort((left, right) => left.videoTimeMs - right.videoTimeMs);

  if (qualitySamples.length === 0) {
    // Cap telemetry times to the known video duration to prevent trace extending past video end.
    const maxTelemetryMs = annotationDurationMs > 0 ? annotationDurationMs : Infinity;

    const telemetryTimes = Array.from(
      new Set(
        timeline
          .map((event) => Math.max(0, Math.round(event.videoTimeMs)))
          .filter((value) => Number.isFinite(value) && value <= maxTelemetryMs)
      )
    ).sort((left, right) => left - right);

    return telemetryTimes.map((videoTimeMs) => {
      const dial = dialValueAt(videoTimeMs);
      const fallbackRewardProxy =
        typeof dial === 'number'
          ? Number(clampNumber(18 + dial * 0.55, 0, 100).toFixed(6))
          : undefined;

      const dialNorm = typeof dial === 'number' ? dial / 100 : 0.5;
      const phaseRad = (videoTimeMs / Math.max(maxTelemetryMs === Infinity ? 30000 : maxTelemetryMs, 1)) * 2 * Math.PI;
      const fallbackBlinkRate = Number(
        clampNumber(
          TRACE_DEFAULT_BLINK_BASELINE_RATE
            - 0.08 * dialNorm
            + 0.05 * Math.sin(phaseRad * 3.1)
            + 0.03 * Math.cos(phaseRad * 5.7),
          0.05,
          0.55
        ).toFixed(6)
      );

      return {
        t_ms: videoTimeMs,
        video_time_ms: videoTimeMs,
        face_ok: false,
        face_presence_confidence: 0,
        brightness: 0,
        blur: 0,
        landmarks_ok: false,
        landmarks_confidence: 0,
        eye_openness: 0.45,
        blink: 0,
        blink_confidence: 0,
        rolling_blink_rate: fallbackBlinkRate,
        blink_inhibition_score: 0,
        blink_inhibition_active: false,
        blink_baseline_rate: TRACE_DEFAULT_BLINK_BASELINE_RATE,
        dial,
        reward_proxy: fallbackRewardProxy,
        au: defaultTraceAu,
        au_norm: defaultTraceAu,
        au_confidence: 0,
        head_pose: {
          yaw: null,
          pitch: null,
          roll: null
        },
        head_pose_confidence: 0,
        head_pose_valid_pct: 0,
        gaze_on_screen_proxy: 0.5,
        gaze_on_screen_confidence: 0,
        fps: 0,
        fps_stability: 0,
        face_visible_pct: 0,
        occlusion_score: 1,
        quality_score: 0.2,
        quality_confidence: 0,
        tracking_confidence: 0,
        quality_flags: ['face_lost']
      };
    });
  }

  const blinkWindowMs = 5000;
  const blinkEventTimes: number[] = [];

  return qualitySamples.map((sample, index) => {
    const previousSample = qualitySamples[Math.max(0, index - 1)];
    const videoTimeMs = Math.max(0, Math.round(sample.videoTimeMs));
    const trackingConfidence = Number(clampNumber(sample.trackingConfidence, 0, 1).toFixed(6));
    const facePresenceConfidence = Number(clampNumber(sample.faceVisiblePct, 0, 1).toFixed(6));
    const headPoseValidPct = Number(clampNumber(sample.headPoseValidPct, 0, 1).toFixed(6));
    const occlusionScore = Number(clampNumber(sample.occlusionScore, 0, 1).toFixed(6));
    const qualityScore = Number(clampNumber(sample.qualityScore, 0, 1).toFixed(6));

    const deltaBrightness = Math.abs(sample.brightness - previousSample.brightness);
    const deltaBlur = Math.abs(sample.blur - previousSample.blur);
    const deltaFaceVisible = Math.abs(sample.faceVisiblePct - previousSample.faceVisiblePct);
    const deltaHeadPose = Math.abs(sample.headPoseValidPct - previousSample.headPoseValidPct);
    const confidenceDrop = Math.max(0, previousSample.trackingConfidence - sample.trackingConfidence);
    const occlusionRise = Math.max(0, sample.occlusionScore - previousSample.occlusionScore);

    const expressionMotion = clampNumber(
      (deltaBrightness / 26 +
        deltaBlur / 240 +
        deltaFaceVisible * 2.2 +
        deltaHeadPose * 1.8 +
        occlusionRise * 1.6 +
        confidenceDrop * 1.4) /
        6,
      0,
      1
    );

    const blinkScore = clampNumber(
      deltaFaceVisible * 2.2 +
        occlusionRise * 1.9 +
        confidenceDrop * 1.6 +
        Math.max(0, 0.55 - sample.faceVisiblePct) * 0.8 +
        expressionMotion * 0.35 +
        (sample.faceDetected ? 0 : 0.75),
      0,
      2
    );
    const blink: 0 | 1 = blinkScore >= 0.72 ? 1 : 0;
    if (blink === 1) {
      blinkEventTimes.push(videoTimeMs);
    }
    while (blinkEventTimes.length > 0 && blinkEventTimes[0] < videoTimeMs - blinkWindowMs) {
      blinkEventTimes.shift();
    }
    const effectiveBlinkWindowMs = Math.max(
      2000,
      Math.min(blinkWindowMs, videoTimeMs + QUALITY_SAMPLE_WINDOW_MS)
    );
    const rollingBlinkRate = Number(
      clampNumber((blinkEventTimes.length * 1000) / effectiveBlinkWindowMs, 0, 1.2).toFixed(6)
    );
    const blinkInhibitionScore = Number(
      clampNumber(
        (TRACE_DEFAULT_BLINK_BASELINE_RATE - rollingBlinkRate) /
          Math.max(TRACE_DEFAULT_BLINK_BASELINE_RATE * 1.8, 1e-3),
        -1,
        1
      ).toFixed(6)
    );

    const gazeProxy = Number(
      clampNumber(0.6 * facePresenceConfidence + 0.4 * headPoseValidPct, 0, 1).toFixed(6)
    );
    const eyeOpenness = Number(
      clampNumber((sample.faceDetected ? 0.84 : 0.45) - blink * 0.58 - occlusionRise * 0.08, 0, 1).toFixed(6)
    );
    const landmarksConfidence = Number(clampNumber(trackingConfidence * 0.92, 0, 1).toFixed(6));
    const auConfidence = Number(clampNumber(trackingConfidence * 0.85, 0, 1).toFixed(6));
    const blinkConfidence = Number(
      clampNumber(
        trackingConfidence * (0.45 + expressionMotion * 0.35 + Math.min(deltaFaceVisible * 0.4, 0.2)),
        0,
        1
      ).toFixed(6)
    );

    const dial = dialValueAt(videoTimeMs);
    const dialForReward = typeof dial === 'number' ? dial : 40 + qualityScore * 35;
    const dialNormalized = (dialForReward - 50) / 50;
    const expressionSupport = clampNumber(
      0.5 * expressionMotion + 0.25 * facePresenceConfidence + 0.25 * headPoseValidPct,
      0,
      1
    );

    const au12 = Number(
      clampNumber(
        0.03 +
          Math.max(0, dialNormalized) * 0.12 +
          expressionSupport * 0.08 -
          occlusionScore * 0.05,
        0,
        0.45
      ).toFixed(4)
    );
    const au6 = Number(
      clampNumber(
        0.02 +
          Math.max(0, dialNormalized) * 0.08 +
          expressionSupport * 0.06 +
          headPoseValidPct * 0.04 -
          occlusionScore * 0.04,
        0,
        0.4
      ).toFixed(4)
    );
    const au4 = Number(
      clampNumber(
        0.03 +
          Math.max(0, -dialNormalized) * 0.12 +
          occlusionScore * 0.12 +
          (1 - headPoseValidPct) * 0.07 +
          blink * 0.04 +
          expressionMotion * 0.03,
        0,
        0.45
      ).toFixed(4)
    );
    const au = {
      AU04: au4,
      AU06: au6,
      AU12: au12,
      AU45: blink,
      AU25: Number(clampNumber(0.02 + au12 * 0.35, 0, 0.25).toFixed(4)),
      AU26: Number(clampNumber(0.02 + au12 * 0.4, 0, 0.25).toFixed(4))
    };

    const rewardProxy = Number(
      clampNumber(
        26 +
          dialForReward * 0.43 +
          au12 * 28 +
          au6 * 16 -
          au4 * 12 +
          blinkInhibitionScore * 10 +
          trackingConfidence * 6 +
          qualityScore * 5 -
          occlusionScore * 10,
        0,
        100
      ).toFixed(6)
    );

    const headPoseInstability = clampNumber(1 - headPoseValidPct, 0, 1);

    return {
      t_ms: videoTimeMs,
      video_time_ms: videoTimeMs,
      face_ok: Boolean(
        sample.faceDetected && facePresenceConfidence >= 0.5 && !sample.qualityFlags.includes('face_lost')
      ),
      face_presence_confidence: facePresenceConfidence,
      brightness: Number(sample.brightness.toFixed(3)),
      blur: Number(sample.blur.toFixed(3)),
      landmarks_ok: sample.faceDetected && landmarksConfidence >= 0.35,
      landmarks_confidence: landmarksConfidence,
      eye_openness: eyeOpenness,
      blink,
      blink_confidence: blinkConfidence,
      rolling_blink_rate: rollingBlinkRate,
      blink_inhibition_score: blinkInhibitionScore,
      blink_inhibition_active: blinkInhibitionScore >= 0.35,
      blink_baseline_rate: TRACE_DEFAULT_BLINK_BASELINE_RATE,
      dial: typeof dial === 'number' ? Number(dial.toFixed(2)) : undefined,
      reward_proxy: rewardProxy,
      au,
      au_norm: au,
      au_confidence: auConfidence,
      head_pose: {
        yaw: Number((headPoseInstability * 24).toFixed(6)),
        pitch: Number((headPoseInstability * 14).toFixed(6)),
        roll: Number((headPoseInstability * 10).toFixed(6))
      },
      head_pose_confidence: trackingConfidence,
      head_pose_valid_pct: headPoseValidPct,
      gaze_on_screen_proxy: gazeProxy,
      gaze_on_screen_confidence: trackingConfidence,
      fps: Number(sample.fps.toFixed(3)),
      fps_stability: Number(clampNumber(sample.fpsStability, 0, 1).toFixed(6)),
      face_visible_pct: facePresenceConfidence,
      occlusion_score: occlusionScore,
      quality_score: qualityScore,
      quality_confidence: trackingConfidence,
      tracking_confidence: trackingConfidence,
      quality_flags: [...sample.qualityFlags]
    };
  });
};
