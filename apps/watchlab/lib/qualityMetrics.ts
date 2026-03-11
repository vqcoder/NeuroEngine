export type QualityFlag = 'low_light' | 'blur' | 'face_lost' | 'high_yaw_pitch';

export type QualitySample = {
  id: string;
  wallTimeMs: number;
  videoTimeMs: number;
  sampleWindowMs: number;
  brightness: number;
  brightnessScore: number;
  blur: number;
  blurScore: number;
  fps: number;
  fpsStability: number;
  faceDetected: boolean;
  faceVisiblePct: number;
  headPoseValidPct: number;
  occlusionScore: number;
  qualityScore: number;
  trackingConfidence: number;
  qualityFlags: QualityFlag[];
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

export const brightnessScore = (brightness: number) =>
  Number(clamp01(1 - Math.abs(brightness - 115) / 120).toFixed(6));

export const blurScore = (blur: number) => Number(clamp01(blur / 220).toFixed(6));

export const computeFpsStability = (fpsSamples: number[]) => {
  const samples = fpsSamples.filter((value) => Number.isFinite(value) && value > 0);
  if (samples.length === 0) {
    return 0;
  }
  if (samples.length === 1) {
    return 1;
  }

  const mean =
    samples.reduce((total, value) => total + value, 0) / Math.max(samples.length, 1);
  const variance =
    samples.reduce((total, value) => total + (value - mean) ** 2, 0) /
    Math.max(samples.length, 1);
  const stdDev = Math.sqrt(variance);
  const coeffVar = mean > 0 ? stdDev / mean : 1;
  const variationScore = clamp01(1 - coeffVar / 0.35);
  const throughputScore = clamp01(mean / 12);
  return Number((0.65 * variationScore + 0.35 * throughputScore).toFixed(6));
};

export const computeQualityScore = ({
  brightness,
  blur,
  fpsStability,
  faceVisiblePct,
  occlusionScore,
  headPoseValidPct
}: {
  brightness: number;
  blur: number;
  fpsStability: number;
  faceVisiblePct: number;
  occlusionScore: number;
  headPoseValidPct: number;
}) => {
  const litScore = brightnessScore(brightness);
  const score =
    0.22 * litScore +
    0.2 * blurScore(blur) +
    0.2 * clamp01(fpsStability) +
    0.18 * clamp01(faceVisiblePct) +
    0.12 * (1 - clamp01(occlusionScore)) +
    0.08 * clamp01(headPoseValidPct);
  const brightnessGate = 0.35 + 0.65 * litScore;
  return Number(clamp01(score * brightnessGate).toFixed(6));
};

export const computeTrackingConfidence = ({
  faceVisiblePct,
  headPoseValidPct,
  fpsStability,
  qualityScore,
  occlusionScore
}: {
  faceVisiblePct: number;
  headPoseValidPct: number;
  fpsStability: number;
  qualityScore: number;
  occlusionScore: number;
}) => {
  const confidence =
    0.3 * clamp01(faceVisiblePct) +
    0.25 * clamp01(headPoseValidPct) +
    0.2 * clamp01(fpsStability) +
    0.15 * clamp01(qualityScore) +
    0.1 * (1 - clamp01(occlusionScore));
  return Number(clamp01(confidence).toFixed(6));
};

export const detectQualityFlags = ({
  brightness,
  brightnessScore: litScore,
  blurScore: sharpness,
  faceVisiblePct,
  headPoseValidPct
}: {
  brightness: number;
  brightnessScore: number;
  blurScore: number;
  faceVisiblePct: number;
  headPoseValidPct: number;
}): QualityFlag[] => {
  const flags: QualityFlag[] = [];
  if (brightness < 45 || litScore < 0.45) {
    flags.push('low_light');
  }
  if (sharpness < 0.4) {
    flags.push('blur');
  }
  if (faceVisiblePct < 0.5) {
    flags.push('face_lost');
  }
  if (headPoseValidPct < 0.6) {
    flags.push('high_yaw_pitch');
  }
  return flags;
};

export type LowConfidenceWindow = {
  startVideoTimeMs: number;
  endVideoTimeMs: number;
  meanTrackingConfidence: number;
};

export const detectLowConfidenceWindows = (
  samples: QualitySample[],
  threshold = 0.5
): LowConfidenceWindow[] => {
  if (samples.length === 0) {
    return [];
  }
  const ordered = [...samples].sort((a, b) => a.videoTimeMs - b.videoTimeMs);
  const windows: LowConfidenceWindow[] = [];
  let activeStart: number | null = null;
  let activeEnd: number | null = null;
  let activeValues: number[] = [];

  for (const sample of ordered) {
    const isLow =
      sample.trackingConfidence < threshold ||
      sample.qualityFlags.some((flag) =>
        ['low_light', 'blur', 'face_lost', 'high_yaw_pitch'].includes(flag)
      );
    if (isLow) {
      if (activeStart === null) {
        activeStart = sample.videoTimeMs;
      }
      activeEnd = sample.videoTimeMs + sample.sampleWindowMs;
      activeValues.push(sample.trackingConfidence);
      continue;
    }

    if (activeStart !== null && activeEnd !== null) {
      windows.push({
        startVideoTimeMs: activeStart,
        endVideoTimeMs: activeEnd,
        meanTrackingConfidence:
          activeValues.reduce((total, value) => total + value, 0) /
          Math.max(activeValues.length, 1)
      });
      activeStart = null;
      activeEnd = null;
      activeValues = [];
    }
  }

  if (activeStart !== null && activeEnd !== null) {
    windows.push({
      startVideoTimeMs: activeStart,
      endVideoTimeMs: activeEnd,
      meanTrackingConfidence:
        activeValues.reduce((total, value) => total + value, 0) /
        Math.max(activeValues.length, 1)
    });
  }

  return windows.map((window) => ({
    ...window,
    meanTrackingConfidence: Number(window.meanTrackingConfidence.toFixed(6))
  }));
};
