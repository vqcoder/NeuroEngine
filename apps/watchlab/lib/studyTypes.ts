// ---------------------------------------------------------------------------
// Types, constants, and small utilities extracted from study-client.tsx (A21)
// ---------------------------------------------------------------------------

export type StudyConfig = {
  studyId: string;
  videoId: string;
  title: string;
  videoUrl: string;
  originalVideoUrl?: string | null;
  dialEnabled: boolean;
  requireWebcam: boolean;
  micEnabled: boolean;
};

export type FrontendDiagnosticSeverity = 'info' | 'warning' | 'error';

export type StudyStage = 'onboarding' | 'camera' | 'mic_check' | 'watch' | 'annotation' | 'survey' | 'next_video' | 'complete';

export type WebcamStatus = 'idle' | 'requesting' | 'granted' | 'denied';

export type BrowserFaceDetectionResult = {
  boundingBox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
};

export type QualityState = {
  brightness: number;
  brightnessScore: number;
  blur: number;
  blurScore: number;
  brightnessOk: boolean;
  faceDetected: boolean;
  faceVisiblePct: number;
  headPoseValidPct: number;
  occlusionScore: number;
  faceOk: boolean;
  fps: number;
  fpsStability: number;
  fpsOk: boolean;
  trackingConfidence: number;
  qualityScore: number;
  pass: boolean;
  qualityFlags: string[];
  notes: string[];
};

export type FrameCounterState = {
  active: boolean;
  frames: number;
  lastSampleMs: number;
  fps: number;
  sampleTimerId: number | null;
  callbackHandle: number | null;
  callbackMode: 'video-frame' | 'animation-frame' | null;
};

export const markerTypes = [
  'engaging_moment',
  'confusing_moment',
  'stop_watching_moment',
  'cta_landed_moment'
] as const;

export type MarkerType = (typeof markerTypes)[number];

export const markerLabels: Record<MarkerType, string> = {
  engaging_moment: 'Engaging moment',
  confusing_moment: 'Confusing moment',
  stop_watching_moment: 'Wanted to stop watching',
  cta_landed_moment: 'CTA/key message landed'
};

export type SurveyAnalyticsHighlightCategory =
  | 'engagement'
  | 'confusion'
  | 'drop'
  | 'cta'
  | 'playback'
  | 'quality';

export type SurveyAnalyticsHighlight = {
  id: string;
  videoTimeMs: number;
  category: SurveyAnalyticsHighlightCategory;
  title: string;
  detail: string;
  signalScore: number;
};

export const analyticsCategoryLabel: Record<SurveyAnalyticsHighlightCategory, string> = {
  engagement: 'Engagement',
  confusion: 'Confusion',
  drop: 'Attention drop',
  cta: 'CTA',
  playback: 'Playback behavior',
  quality: 'Tracking quality'
};

export const defaultTraceAu = {
  AU04: 0,
  AU06: 0,
  AU12: 0,
  AU45: 0,
  AU25: 0,
  AU26: 0
} as const;

export const QUALITY_SAMPLE_INTERVAL_MS = 250;
export const QUALITY_SAMPLE_WINDOW_MS = QUALITY_SAMPLE_INTERVAL_MS;
export const TRACE_DEFAULT_BLINK_BASELINE_RATE = 0.22;

export const clampNumber = (value: number, min: number, max: number): number => {
  return Math.min(Math.max(value, min), max);
};

export const DEFAULT_QUALITY: QualityState = {
  brightness: 0,
  brightnessScore: 0,
  blur: 0,
  blurScore: 0,
  brightnessOk: false,
  faceDetected: false,
  faceVisiblePct: 0,
  headPoseValidPct: 0,
  occlusionScore: 1,
  faceOk: false,
  fps: 0,
  fpsStability: 0,
  fpsOk: false,
  trackingConfidence: 0,
  qualityScore: 0,
  pass: false,
  qualityFlags: [],
  notes: ['No camera metrics available yet.']
};

export const MAX_STORED_FRAMES = 240;

export const emptyConfig: StudyConfig = {
  studyId: '',
  videoId: 'demo-video',
  title: 'Study Session',
  videoUrl: '',
  originalVideoUrl: null,
  dialEnabled: false,
  requireWebcam: false,
  micEnabled: false
};
