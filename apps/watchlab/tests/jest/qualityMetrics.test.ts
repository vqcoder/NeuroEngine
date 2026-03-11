import {
  computeFpsStability,
  detectLowConfidenceWindows,
  detectQualityFlags,
  brightnessScore,
  blurScore,
  type QualitySample
} from '@/lib/qualityMetrics';

describe('quality metrics thresholds and window detection', () => {
  test('detectQualityFlags marks low-light, blur, face loss, and high yaw/pitch windows', () => {
    const flags = detectQualityFlags({
      brightness: 30,
      brightnessScore: brightnessScore(30),
      blurScore: blurScore(20),
      faceVisiblePct: 0.3,
      headPoseValidPct: 0.2
    });

    expect(flags).toEqual(['low_light', 'blur', 'face_lost', 'high_yaw_pitch']);
  });

  test('detectQualityFlags remains empty when thresholds pass', () => {
    const flags = detectQualityFlags({
      brightness: 118,
      brightnessScore: brightnessScore(118),
      blurScore: blurScore(260),
      faceVisiblePct: 0.95,
      headPoseValidPct: 0.9
    });

    expect(flags).toEqual([]);
  });

  test('detectLowConfidenceWindows merges contiguous low-confidence samples', () => {
    const samples: QualitySample[] = [
      {
        id: '00000000-0000-4000-8000-000000000001',
        wallTimeMs: 0,
        videoTimeMs: 0,
        sampleWindowMs: 1000,
        brightness: 110,
        brightnessScore: 0.95,
        blur: 180,
        blurScore: 0.82,
        fps: 10,
        fpsStability: 0.9,
        faceDetected: true,
        faceVisiblePct: 0.95,
        headPoseValidPct: 0.92,
        occlusionScore: 0.1,
        qualityScore: 0.88,
        trackingConfidence: 0.84,
        qualityFlags: []
      },
      {
        id: '00000000-0000-4000-8000-000000000002',
        wallTimeMs: 1000,
        videoTimeMs: 1000,
        sampleWindowMs: 1000,
        brightness: 58,
        brightnessScore: 0.5,
        blur: 90,
        blurScore: 0.4,
        fps: 9,
        fpsStability: 0.65,
        faceDetected: true,
        faceVisiblePct: 0.64,
        headPoseValidPct: 0.61,
        occlusionScore: 0.28,
        qualityScore: 0.49,
        trackingConfidence: 0.46,
        qualityFlags: []
      },
      {
        id: '00000000-0000-4000-8000-000000000003',
        wallTimeMs: 2000,
        videoTimeMs: 2000,
        sampleWindowMs: 1000,
        brightness: 53,
        brightnessScore: 0.48,
        blur: 75,
        blurScore: 0.34,
        fps: 8,
        fpsStability: 0.55,
        faceDetected: true,
        faceVisiblePct: 0.58,
        headPoseValidPct: 0.57,
        occlusionScore: 0.33,
        qualityScore: 0.45,
        trackingConfidence: 0.44,
        qualityFlags: []
      },
      {
        id: '00000000-0000-4000-8000-000000000004',
        wallTimeMs: 3000,
        videoTimeMs: 3000,
        sampleWindowMs: 1000,
        brightness: 42,
        brightnessScore: 0.39,
        blur: 35,
        blurScore: 0.15,
        fps: 10,
        fpsStability: 0.72,
        faceDetected: true,
        faceVisiblePct: 0.71,
        headPoseValidPct: 0.7,
        occlusionScore: 0.21,
        qualityScore: 0.41,
        trackingConfidence: 0.62,
        qualityFlags: ['low_light']
      },
      {
        id: '00000000-0000-4000-8000-000000000005',
        wallTimeMs: 4000,
        videoTimeMs: 4000,
        sampleWindowMs: 1000,
        brightness: 120,
        brightnessScore: 0.98,
        blur: 200,
        blurScore: 0.91,
        fps: 10,
        fpsStability: 0.93,
        faceDetected: true,
        faceVisiblePct: 0.96,
        headPoseValidPct: 0.93,
        occlusionScore: 0.08,
        qualityScore: 0.9,
        trackingConfidence: 0.88,
        qualityFlags: []
      }
    ];

    const windows = detectLowConfidenceWindows(samples, 0.5);

    expect(windows).toEqual([
      {
        startVideoTimeMs: 1000,
        endVideoTimeMs: 4000,
        meanTrackingConfidence: 0.506667
      }
    ]);
  });

  test('computeFpsStability scores stable fps higher than jittery fps', () => {
    const stable = computeFpsStability([10.1, 9.9, 10.0, 10.2, 9.8]);
    const unstable = computeFpsStability([4.0, 15.0, 2.0, 14.0, 3.0]);

    expect(stable).toBeGreaterThan(unstable);
    expect(stable).toBeGreaterThan(0.7);
    expect(unstable).toBeLessThan(0.55);
  });
});
