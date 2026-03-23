/**
 * useWebcam — Webcam state, refs, and control functions extracted from StudyClient.
 *
 * Owns:
 *   State:  webcamStatus, quality, capturedFrameCount
 *   Refs:   streamRef, webcamVideoRef, captureCanvasRef, framesRef, framePointersRef
 *   Fns:    startWebcamChecks, stopWebcamCaptureLoops, startFrameCapture, bypassWebcam
 */

import { useRef, useState } from 'react';
import type { MutableRefObject, RefObject } from 'react';
import {
  type FramePointer,
  type QualitySample,
  type TimelineEvent,
  type UploadFrame,
} from '@/lib/schema';
import {
  brightnessScore,
  blurScore,
  computeFpsStability,
  computeQualityScore,
  computeTrackingConfidence,
  detectQualityFlags,
} from '@/lib/qualityMetrics';
import {
  type BrowserFaceDetectionResult,
  type FrameCounterState,
  type QualityState,
  type StudyStage,
  type WebcamStatus,
  DEFAULT_QUALITY,
  MAX_STORED_FRAMES,
  QUALITY_SAMPLE_INTERVAL_MS,
  QUALITY_SAMPLE_WINDOW_MS,
} from '@/lib/studyTypes';
import { safeUuid } from '@/lib/studyHelpers';

// ── Types ──────────────────────────────────────────────────────────────────

export interface UseWebcamDeps {
  /** Append a timeline event. */
  appendEvent: (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward?: boolean,
    explicitVideoTimeMs?: number,
  ) => void;
  /** Sample the current synced video time. */
  sampleSyncedVideoTimeMs: (allowBackward: boolean) => number;
  /** Ref to the current study stage. */
  stageRef: MutableRefObject<StudyStage>;
  /** Whether the study config requires a webcam. */
  requireWebcam: boolean;
}

export interface UseWebcamReturn {
  // State
  webcamStatus: WebcamStatus;
  quality: QualityState;
  capturedFrameCount: number;

  // Refs
  streamRef: MutableRefObject<MediaStream | null>;
  webcamVideoRef: RefObject<HTMLVideoElement | null>;
  captureCanvasRef: RefObject<HTMLCanvasElement | null>;
  qualityCanvasRef: RefObject<HTMLCanvasElement | null>;
  framesRef: MutableRefObject<UploadFrame[]>;
  framePointersRef: MutableRefObject<FramePointer[]>;
  qualitySamplesRef: MutableRefObject<QualitySample[]>;
  frameCounterRef: MutableRefObject<FrameCounterState>;

  // Functions
  startWebcamChecks: () => Promise<void>;
  stopWebcamCaptureLoops: () => void;
  startFrameCapture: () => void;
  bypassWebcam: () => void;
  stopWebcam: () => void;
  runQualityCheck: () => Promise<void>;
  startFrameCounter: () => void;

  // Setters exposed for external use (e.g. retry, camera-check)
  setWebcamStatus: React.Dispatch<React.SetStateAction<WebcamStatus>>;
  setQuality: React.Dispatch<React.SetStateAction<QualityState>>;
  setCapturedFrameCount: React.Dispatch<React.SetStateAction<number>>;
  resetQualityBuffers: () => void;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useWebcam(deps: UseWebcamDeps): UseWebcamReturn {
  const { appendEvent, sampleSyncedVideoTimeMs, stageRef, requireWebcam } = deps;

  // State
  const [webcamStatus, setWebcamStatus] = useState<WebcamStatus>('idle');
  const [quality, setQuality] = useState<QualityState>(DEFAULT_QUALITY);
  const [capturedFrameCount, setCapturedFrameCount] = useState(0);

  // Refs
  const streamRef = useRef<MediaStream | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement | null>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const qualityCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const framesRef = useRef<UploadFrame[]>([]);
  const framePointersRef = useRef<FramePointer[]>([]);
  const qualitySamplesRef = useRef<QualitySample[]>([]);
  const qualityCheckInFlightRef = useRef(false);
  const qualityLoopTimerRef = useRef<number | null>(null);
  const frameCaptureTimerRef = useRef<number | null>(null);

  const recentFpsRef = useRef<number[]>([]);
  const recentFaceVisibleRef = useRef<boolean[]>([]);
  const recentHeadPoseValidRef = useRef<boolean[]>([]);

  const frameCounterRef = useRef<FrameCounterState>({
    active: false,
    frames: 0,
    lastSampleMs: 0,
    fps: 0,
    sampleTimerId: null,
    callbackHandle: null,
    callbackMode: null,
  });

  const faceDetectorRef = useRef<{
    detect: (input: HTMLVideoElement) => Promise<BrowserFaceDetectionResult[]>;
  } | null>(null);

  // ── Helpers ────────────────────────────────────────────────────────────

  const pushRollingSample = <T,>(buffer: T[], value: T, maxSize = 16) => {
    buffer.push(value);
    while (buffer.length > maxSize) {
      buffer.shift();
    }
  };

  const computeMean = (values: number[]) => {
    if (values.length === 0) return 0;
    return values.reduce((total, value) => total + value, 0) / values.length;
  };

  const estimateBlurProxy = (
    pixels: Uint8ClampedArray,
    width: number,
    height: number,
  ): number => {
    if (width < 3 || height < 3) return 0;
    const luminance = new Float32Array(width * height);
    for (let i = 0, p = 0; i < luminance.length; i += 1, p += 4) {
      luminance[i] = 0.299 * pixels[p] + 0.587 * pixels[p + 1] + 0.114 * pixels[p + 2];
    }
    let laplacianEnergy = 0;
    let sampleCount = 0;
    for (let y = 1; y < height - 1; y += 1) {
      for (let x = 1; x < width - 1; x += 1) {
        const center = y * width + x;
        const laplacian =
          4 * luminance[center] -
          luminance[center - 1] -
          luminance[center + 1] -
          luminance[center - width] -
          luminance[center + width];
        laplacianEnergy += laplacian * laplacian;
        sampleCount += 1;
      }
    }
    if (sampleCount === 0) return 0;
    return Number((laplacianEnergy / sampleCount).toFixed(6));
  };

  // ── Frame counter ─────────────────────────────────────────────────────

  const stopFrameCounter = () => {
    const counter = frameCounterRef.current;
    counter.active = false;
    if (counter.sampleTimerId !== null) {
      window.clearInterval(counter.sampleTimerId);
      counter.sampleTimerId = null;
    }

    const webcamVideo = webcamVideoRef.current as HTMLVideoElement & {
      cancelVideoFrameCallback?: (handle: number) => void;
    };

    if (counter.callbackHandle !== null) {
      if (counter.callbackMode === 'video-frame' && webcamVideo?.cancelVideoFrameCallback) {
        webcamVideo.cancelVideoFrameCallback(counter.callbackHandle);
      } else if (counter.callbackMode === 'animation-frame') {
        window.cancelAnimationFrame(counter.callbackHandle);
      }
      counter.callbackHandle = null;
    }
    counter.callbackMode = null;
    counter.frames = 0;
    counter.fps = 0;
  };

  const startFrameCounter = () => {
    const webcamVideo = webcamVideoRef.current as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: () => void) => number;
    };
    if (!webcamVideo) return;

    stopFrameCounter();

    const counter = frameCounterRef.current;
    counter.active = true;
    counter.frames = 0;
    counter.lastSampleMs = performance.now();

    const countFrame = () => {
      if (!counter.active) return;
      counter.frames += 1;
      if (webcamVideo.requestVideoFrameCallback) {
        counter.callbackHandle = webcamVideo.requestVideoFrameCallback(countFrame);
        counter.callbackMode = 'video-frame';
      } else {
        counter.callbackHandle = window.requestAnimationFrame(countFrame);
        counter.callbackMode = 'animation-frame';
      }
    };

    countFrame();

    counter.sampleTimerId = window.setInterval(() => {
      const now = performance.now();
      const elapsed = now - counter.lastSampleMs;
      if (elapsed > 0) {
        counter.fps = Number(((counter.frames * 1000) / elapsed).toFixed(1));
      }
      counter.frames = 0;
      counter.lastSampleMs = now;
    }, 1000);
  };

  // ── Capture loops ─────────────────────────────────────────────────────

  const stopWebcamCaptureLoops = () => {
    if (qualityLoopTimerRef.current !== null) {
      window.clearInterval(qualityLoopTimerRef.current);
      qualityLoopTimerRef.current = null;
    }
    if (frameCaptureTimerRef.current !== null) {
      window.clearInterval(frameCaptureTimerRef.current);
      frameCaptureTimerRef.current = null;
    }
    stopFrameCounter();
  };

  const stopWebcam = () => {
    stopWebcamCaptureLoops();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (webcamVideoRef.current) {
      webcamVideoRef.current.srcObject = null;
    }
  };

  const startFrameCapture = () => {
    const canvas = captureCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    canvas.width = 224;
    canvas.height = 224;

    if (frameCaptureTimerRef.current !== null) {
      window.clearInterval(frameCaptureTimerRef.current);
    }

    frameCaptureTimerRef.current = window.setInterval(() => {
      if (!streamRef.current) return;
      const webcamVideo = webcamVideoRef.current;
      if (!webcamVideo || webcamVideo.readyState < 2) return;

      ctx.drawImage(webcamVideo, 0, 0, 224, 224);
      const jpegData = canvas.toDataURL('image/jpeg', 0.7).split(',')[1] ?? '';
      const timestampMs = Date.now();
      const syncedVideoTimeMs = sampleSyncedVideoTimeMs(false);

      if (framesRef.current.length < MAX_STORED_FRAMES) {
        framesRef.current.push({
          id: safeUuid(),
          timestampMs,
          videoTimeMs: syncedVideoTimeMs,
          jpegBase64: jpegData,
        });
      } else {
        framePointersRef.current.push({
          id: safeUuid(),
          timestampMs,
          videoTimeMs: syncedVideoTimeMs,
          pointer: `memory-frame-${framesRef.current.length + framePointersRef.current.length}`,
        });
      }
      setCapturedFrameCount(framesRef.current.length + framePointersRef.current.length);
    }, 200);
  };

  // ── Quality check ─────────────────────────────────────────────────────

  const runQualityCheck = async () => {
    if (qualityCheckInFlightRef.current) return;

    const webcamVideo = webcamVideoRef.current;
    const canvas = qualityCanvasRef.current;
    if (!webcamVideo || !canvas || webcamVideo.readyState < 2) return;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return;

    qualityCheckInFlightRef.current = true;
    try {
      const sampleWidth = 64;
      const sampleHeight = 48;
      canvas.width = sampleWidth;
      canvas.height = sampleHeight;
      ctx.drawImage(webcamVideo, 0, 0, sampleWidth, sampleHeight);
      const pixels = ctx.getImageData(0, 0, sampleWidth, sampleHeight).data;

      let sum = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        sum += 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
      }
      const brightness = Number((sum / (sampleWidth * sampleHeight)).toFixed(1));
      const blur = estimateBlurProxy(pixels, sampleWidth, sampleHeight);
      const litScore = brightnessScore(brightness);
      const sharpnessScore = blurScore(blur);

      let faceDetected = false;
      let faceOk = false;
      let headPoseValid = false;
      let occlusionScore = 1;
      let centerOffset = 1;
      let borderTouchRatio = 1;
      let faceAreaRatio = 0;
      const notes: string[] = [];
      let faceDetectionAvailable = true;

      const FaceDetectorCtor = (
        window as unknown as {
          FaceDetector?: new () => {
            detect: (input: HTMLVideoElement) => Promise<BrowserFaceDetectionResult[]>;
          };
        }
      ).FaceDetector;

      if (FaceDetectorCtor) {
        if (!faceDetectorRef.current) {
          faceDetectorRef.current = new FaceDetectorCtor();
        }
        try {
          const faces = await faceDetectorRef.current.detect(webcamVideo);
          faceDetected = faces.length > 0;
          const firstFace = faces[0];
          const box = firstFace?.boundingBox;
          if (box && box.width > 0 && box.height > 0) {
            faceAreaRatio = Math.max(
              0,
              Math.min((box.width * box.height) / (sampleWidth * sampleHeight), 1),
            );
            const centerX = box.x + box.width / 2;
            const centerY = box.y + box.height / 2;
            const dx = Math.abs(centerX - sampleWidth / 2) / Math.max(sampleWidth / 2, 1);
            const dy = Math.abs(centerY - sampleHeight / 2) / Math.max(sampleHeight / 2, 1);
            centerOffset = Math.max(0, Math.min((dx + dy) / 2, 1));

            let touches = 0;
            const marginX = sampleWidth * 0.04;
            const marginY = sampleHeight * 0.04;
            if (box.x <= marginX) touches += 1;
            if (box.x + box.width >= sampleWidth - marginX) touches += 1;
            if (box.y <= marginY) touches += 1;
            if (box.y + box.height >= sampleHeight - marginY) touches += 1;
            borderTouchRatio = touches / 4;
          }
          headPoseValid =
            faceDetected && centerOffset < 0.35 && faceAreaRatio > 0.06 && borderTouchRatio < 0.5;
          const smallFacePenalty = Math.max(0, Math.min((0.06 - faceAreaRatio) / 0.06, 1));
          occlusionScore = Math.max(
            0,
            Math.min(0.55 * borderTouchRatio + 0.45 * smallFacePenalty, 1),
          );
        } catch {
          notes.push('Face detection call failed; reposition your face in view.');
        }
      } else {
        faceDetectionAvailable = false;
        faceDetected = true;
        headPoseValid = true;
        occlusionScore = 0.4;
      }

      const fps = frameCounterRef.current.fps;
      pushRollingSample(recentFpsRef.current, fps, 20);
      pushRollingSample(recentFaceVisibleRef.current, faceDetected, 20);
      pushRollingSample(recentHeadPoseValidRef.current, headPoseValid, 20);

      const fpsStability = computeFpsStability(recentFpsRef.current);
      const faceVisiblePct = computeMean(
        recentFaceVisibleRef.current.map((v) => (v ? 1 : 0)),
      );
      const headPoseValidPct = computeMean(
        recentHeadPoseValidRef.current.map((v) => (v ? 1 : 0)),
      );
      const qualityScore = computeQualityScore({
        brightness, blur, fpsStability, faceVisiblePct, occlusionScore, headPoseValidPct,
      });
      const trackingConfidence = computeTrackingConfidence({
        faceVisiblePct, headPoseValidPct, fpsStability, qualityScore, occlusionScore,
      });
      const qualityFlags = detectQualityFlags({
        brightness, brightnessScore: litScore, blurScore: sharpnessScore,
        faceVisiblePct, headPoseValidPct,
      });

      const brightnessOk = litScore >= 0.45;
      const fpsOk = fps >= 8 || fpsStability >= 0.45;
      faceOk = faceDetected && faceVisiblePct >= 0.5;
      const pass =
        brightnessOk && fpsOk && faceOk && qualityScore >= 0.45 && !qualityFlags.includes('face_lost');

      if (qualityFlags.includes('low_light')) notes.push('Increase front lighting.');
      if (qualityFlags.includes('blur')) notes.push('Camera looks blurry. Clean lens or steady the device.');
      if (qualityFlags.includes('face_lost')) notes.push('Keep your face centered and visible in frame.');
      if (qualityFlags.includes('high_yaw_pitch') && faceDetectionAvailable) {
        notes.push('Face angle is too steep. Face the screen more directly.');
      }
      if (!fpsOk) notes.push('Camera FPS is unstable; close CPU-heavy apps.');
      if (!pass && notes.length === 0) notes.push('Adjust camera position and lighting, then retry.');

      const qualitySample: QualitySample = {
        id: safeUuid(),
        wallTimeMs: Date.now(),
        videoTimeMs: sampleSyncedVideoTimeMs(false),
        sampleWindowMs: QUALITY_SAMPLE_WINDOW_MS,
        brightness,
        brightnessScore: litScore,
        blur,
        blurScore: sharpnessScore,
        fps,
        fpsStability,
        faceDetected,
        faceVisiblePct: Number(faceVisiblePct.toFixed(6)),
        headPoseValidPct: Number(headPoseValidPct.toFixed(6)),
        occlusionScore: Number(occlusionScore.toFixed(6)),
        qualityScore,
        trackingConfidence,
        qualityFlags,
      };
      qualitySamplesRef.current.push(qualitySample);
      if (qualitySamplesRef.current.length > 1200) {
        qualitySamplesRef.current.shift();
      }

      const updated: QualityState = {
        brightness, brightnessScore: litScore, blur, blurScore: sharpnessScore,
        brightnessOk, faceDetected,
        faceVisiblePct: qualitySample.faceVisiblePct,
        headPoseValidPct: qualitySample.headPoseValidPct,
        occlusionScore: qualitySample.occlusionScore,
        faceOk, fps, fpsStability, fpsOk,
        trackingConfidence, qualityScore, pass, qualityFlags, notes,
      };

      setQuality(updated);

      appendEvent('quality_check', {
        brightness, brightnessScore: litScore, blur, blurScore: sharpnessScore,
        brightnessOk, faceDetected,
        faceVisiblePct: qualitySample.faceVisiblePct,
        headPoseValidPct: qualitySample.headPoseValidPct,
        occlusionScore: qualitySample.occlusionScore,
        faceOk, fps, fpsStability, fpsOk, pass, qualityScore, trackingConfidence, qualityFlags,
      }, false, qualitySample.videoTimeMs);
    } finally {
      qualityCheckInFlightRef.current = false;
    }
  };

  // ── Start webcam ──────────────────────────────────────────────────────

  const startWebcamChecks = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setWebcamStatus('denied');
      setQuality({ ...DEFAULT_QUALITY, notes: ['This browser does not support webcam capture.'] });
      appendEvent('webcam_denied', { reason: 'unsupported' });
      return;
    }

    setWebcamStatus('requesting');

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 30, min: 10 } },
      });

      streamRef.current = stream;

      stream.getTracks().forEach((track) => {
        track.addEventListener('ended', () => {
          if (stageRef.current === 'watch' || stageRef.current === 'camera') {
            appendEvent('webcam_device_lost', { trackKind: track.kind });
            setWebcamStatus('denied');
            setQuality({ ...DEFAULT_QUALITY, notes: ['Camera disconnected. Please reconnect and retry.'] });
            stopWebcamCaptureLoops();
            setTimeout(() => {
              if (stageRef.current === 'watch' || stageRef.current === 'camera') {
                void startWebcamChecks();
              }
            }, 2000);
          }
        });
      });

      const webcamVideo = webcamVideoRef.current;
      if (webcamVideo) {
        webcamVideo.srcObject = stream;
        await webcamVideo.play();
      }

      setWebcamStatus('granted');
      appendEvent('webcam_granted');
      startFrameCounter();
      await runQualityCheck();

      qualityLoopTimerRef.current = window.setInterval(() => {
        runQualityCheck().catch(() => {});
      }, QUALITY_SAMPLE_INTERVAL_MS);

      startFrameCapture();
    } catch (error) {
      setWebcamStatus('denied');
      setQuality({
        ...DEFAULT_QUALITY,
        notes: [error instanceof Error ? error.message : 'Webcam permission was denied or unavailable.'],
      });
      appendEvent('webcam_denied', {
        reason: error instanceof Error ? error.message : 'unknown',
      });
    }
  };

  // ── Bypass webcam ─────────────────────────────────────────────────────

  const bypassWebcam = () => {
    if (requireWebcam) return;
    stopWebcam();
    setWebcamStatus('denied');
    setQuality({ ...DEFAULT_QUALITY, notes: ['Proceeding without webcam capture for this session.'] });
    setCapturedFrameCount(0);
    framesRef.current = [];
    framePointersRef.current = [];
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
    appendEvent('webcam_denied', { reason: 'participant_opted_out', optionalPath: true });
  };

  const resetQualityBuffers = () => {
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
  };

  return {
    webcamStatus, quality, capturedFrameCount,
    streamRef, webcamVideoRef, captureCanvasRef, qualityCanvasRef,
    framesRef, framePointersRef, qualitySamplesRef, frameCounterRef,
    startWebcamChecks, stopWebcamCaptureLoops, startFrameCapture,
    bypassWebcam, stopWebcam, runQualityCheck, startFrameCounter,
    setWebcamStatus, setQuality, setCapturedFrameCount,
    resetQualityBuffers,
  };
}
