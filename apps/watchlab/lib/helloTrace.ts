type DialSampleLike = {
  videoTimeMs: number;
  value: number;
};

type TimelineEventLike = {
  videoTimeMs: number;
};

type QualitySampleLike = {
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
};

const ZERO_AU = {
  AU04: 0,
  AU06: 0,
  AU12: 0,
  AU45: 0,
  AU25: 0,
  AU26: 0
};

const clamp = (value: number, min: number, max: number) => {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
};

const clamp01 = (value: number) => clamp(value, 0, 1);

const nearestQualitySample = (
  samples: QualitySampleLike[],
  targetVideoTimeMs: number
): QualitySampleLike | null => {
  if (samples.length === 0) {
    return null;
  }
  let nearest = samples[0];
  let nearestDelta = Math.abs(samples[0].videoTimeMs - targetVideoTimeMs);
  for (let index = 1; index < samples.length; index += 1) {
    const candidate = samples[index];
    const delta = Math.abs(candidate.videoTimeMs - targetVideoTimeMs);
    if (delta < nearestDelta) {
      nearest = candidate;
      nearestDelta = delta;
    }
  }
  return nearest;
};

const buildTimeAxis = (
  dialSamples: DialSampleLike[],
  qualitySamples: QualitySampleLike[],
  eventTimeline: TimelineEventLike[]
) => {
  const maxFromEvents = Math.max(0, ...eventTimeline.map((event) => event.videoTimeMs));
  const maxFromDial = Math.max(0, ...dialSamples.map((sample) => sample.videoTimeMs));
  const maxFromQuality = Math.max(0, ...qualitySamples.map((sample) => sample.videoTimeMs));
  const maxVideoTimeMs = Math.max(5000, maxFromEvents, maxFromDial, maxFromQuality);

  const axis = new Set<number>();
  for (let value = 0; value <= maxVideoTimeMs; value += 1000) {
    axis.add(value);
  }
  dialSamples.forEach((sample) => axis.add(Math.max(0, Math.round(sample.videoTimeMs))));
  qualitySamples.forEach((sample) => axis.add(Math.max(0, Math.round(sample.videoTimeMs))));

  return [...axis].sort((a, b) => a - b);
};

export type PlaceholderTraceRow = {
  t_ms: number;
  video_time_ms: number;
  face_ok: boolean;
  face_presence_confidence: number;
  brightness: number;
  blur: number;
  landmarks_ok: boolean;
  landmarks_confidence: number;
  eye_openness: number;
  blink: 0 | 1;
  blink_confidence: number;
  rolling_blink_rate: number;
  blink_inhibition_score: number;
  blink_inhibition_active: boolean;
  blink_baseline_rate: number;
  dial: number;
  reward_proxy: number;
  au: typeof ZERO_AU;
  au_norm: typeof ZERO_AU;
  au_confidence: number;
  head_pose: { yaw: number; pitch: number; roll: number };
  head_pose_confidence: number;
  head_pose_valid_pct: number;
  gaze_on_screen_proxy: number;
  gaze_on_screen_confidence: number;
  fps: number;
  fps_stability: number;
  face_visible_pct: number;
  occlusion_score: number;
  quality_score: number;
  quality_confidence: number;
  tracking_confidence: number;
  quality_flags: Array<'low_light' | 'blur' | 'face_lost' | 'high_yaw_pitch'>;
};

export function buildFallbackDialSamples(eventTimeline: TimelineEventLike[]): DialSampleLike[] {
  const maxVideoTimeMs = Math.max(5000, ...eventTimeline.map((event) => event.videoTimeMs));
  const samples: DialSampleLike[] = [];

  for (let tMs = 0; tMs <= maxVideoTimeMs; tMs += 1000) {
    samples.push({
      videoTimeMs: tMs,
      value: Number((50 + Math.sin((tMs / 1000) * 0.9) * 12).toFixed(2))
    });
  }

  return samples;
}

export function buildPlaceholderTraceRows(
  dialSamples: DialSampleLike[],
  eventTimeline: TimelineEventLike[],
  qualitySamples: QualitySampleLike[] = []
): PlaceholderTraceRow[] {
  const sourceDial =
    dialSamples.length > 0
      ? [...dialSamples].sort((a, b) => a.videoTimeMs - b.videoTimeMs)
      : buildFallbackDialSamples(eventTimeline);

  const sortedQualitySamples = [...qualitySamples].sort((a, b) => a.videoTimeMs - b.videoTimeMs);
  const timeAxis = buildTimeAxis(sourceDial, sortedQualitySamples, eventTimeline);
  const defaultBlinkBaselineRate = 0.22;

  return timeAxis.map((videoTimeMs) => {
    const seconds = videoTimeMs / 1000;
    const dialSample =
      sourceDial.find((sample) => sample.videoTimeMs === videoTimeMs) ??
      sourceDial[Math.min(Math.floor(videoTimeMs / 1000), Math.max(sourceDial.length - 1, 0))];
    const dial = clamp(dialSample?.value ?? 50, 0, 100);
    const dialNorm = (dial - 50) / 50;

    const blinkSignal = Math.sin(seconds * 2.1) + Math.cos(seconds * 0.8) * 0.25;
    const blink: 0 | 1 = blinkSignal > 0.9 ? 1 : 0;
    const rollingBlinkRate = Number(
      clamp(0.18 + Math.sin(seconds * 0.35) * 0.08 + blink * 0.06, 0, 1.2).toFixed(6)
    );
    const blinkInhibitionScore = Number(
      clamp((defaultBlinkBaselineRate - rollingBlinkRate) / Math.max(defaultBlinkBaselineRate, 1e-3), -1, 1)
        .toFixed(6)
    );

    const au12 = clamp(0.07 + dialNorm * 0.09 + Math.sin(seconds * 0.7) * 0.02, -0.2, 0.35);
    const au6 = clamp(0.05 + dialNorm * 0.05 + Math.cos(seconds * 0.9) * 0.015, -0.15, 0.25);
    const au4 = clamp(0.03 + Math.max(0, -dialNorm) * 0.09 + blink * 0.03, 0, 0.3);

    const quality = nearestQualitySample(sortedQualitySamples, videoTimeMs);
    const faceVisiblePct = clamp01(quality?.faceVisiblePct ?? 1);
    const headPoseValidPct = clamp01(quality?.headPoseValidPct ?? 0.9);
    const occlusionScore = clamp01(quality?.occlusionScore ?? 0.08);
    const qualityScore = clamp01(quality?.qualityScore ?? 0.82);
    const trackingConfidence = clamp01(quality?.trackingConfidence ?? 0.84);
    const fpsStability = clamp01(quality?.fpsStability ?? 0.9);
    const faceDetected = quality?.faceDetected ?? true;
    const brightness = Number((quality?.brightness ?? 72 + Math.sin(seconds * 0.5) * 6).toFixed(2));
    const blur = Number((quality?.blur ?? 155 + Math.cos(seconds * 0.25) * 18).toFixed(6));
    const qualityFlags = quality?.qualityFlags ?? [];
    const facePresenceConfidence = Number(clamp01(faceVisiblePct * (1 - occlusionScore * 0.35)).toFixed(6));
    const landmarksConfidence = Number(
      clamp01(facePresenceConfidence * headPoseValidPct * (1 - occlusionScore * 0.3)).toFixed(6)
    );
    const headPoseConfidence = Number(clamp01(headPoseValidPct * (1 - occlusionScore * 0.2)).toFixed(6));
    const gazeOnScreenProxy = Number(clamp01(0.6 * facePresenceConfidence + 0.4 * headPoseValidPct).toFixed(6));
    const gazeOnScreenConfidence = Number(
      clamp01(0.55 * headPoseConfidence + 0.45 * facePresenceConfidence).toFixed(6)
    );

    const au = {
      AU04: Number(au4.toFixed(4)),
      AU06: Number(au6.toFixed(4)),
      AU12: Number(au12.toFixed(4)),
      AU45: blink,
      AU25: Number(clamp(0.02 + au12 * 0.35, 0, 0.25).toFixed(4)),
      AU26: Number(clamp(0.02 + au12 * 0.4, 0, 0.25).toFixed(4))
    };
    const rewardProxy = Number(
      clamp(
        30 +
          dial * 0.45 +
          au.AU12 * 28 +
          au.AU06 * 16 -
          au.AU04 * 12 +
          blinkInhibitionScore * 9,
        0,
        100
      ).toFixed(6)
    );

    return {
      t_ms: Math.max(Math.round(videoTimeMs), 0),
      video_time_ms: Math.max(Math.round(videoTimeMs), 0),
      face_ok: Boolean(faceDetected && faceVisiblePct >= 0.5 && !qualityFlags.includes('face_lost')),
      face_presence_confidence: facePresenceConfidence,
      brightness,
      blur,
      landmarks_ok: landmarksConfidence >= 0.35,
      landmarks_confidence: landmarksConfidence,
      eye_openness: Number(clamp01(0.82 - blink * 0.6).toFixed(6)),
      blink,
      blink_confidence: Number(clamp01(0.55 * trackingConfidence + 0.45 * landmarksConfidence).toFixed(6)),
      rolling_blink_rate: rollingBlinkRate,
      blink_inhibition_score: blinkInhibitionScore,
      blink_inhibition_active: blinkInhibitionScore >= 0.35,
      blink_baseline_rate: defaultBlinkBaselineRate,
      dial: Number(dial.toFixed(2)),
      reward_proxy: rewardProxy,
      au,
      au_norm: au,
      au_confidence: Number(clamp01(0.6 * trackingConfidence + 0.4 * landmarksConfidence).toFixed(6)),
      head_pose: {
        yaw: Number(((1 - headPoseValidPct) * 28).toFixed(6)),
        pitch: Number(((1 - headPoseValidPct) * 16).toFixed(6)),
        roll: Number(((1 - headPoseValidPct) * 11).toFixed(6))
      },
      head_pose_confidence: headPoseConfidence,
      head_pose_valid_pct: headPoseValidPct,
      gaze_on_screen_proxy: gazeOnScreenProxy,
      gaze_on_screen_confidence: gazeOnScreenConfidence,
      fps: Number((quality?.fps ?? 24).toFixed(6)),
      fps_stability: fpsStability,
      face_visible_pct: faceVisiblePct,
      occlusion_score: occlusionScore,
      quality_score: qualityScore,
      quality_confidence: trackingConfidence,
      tracking_confidence: trackingConfidence,
      quality_flags: qualityFlags
    };
  });
}
