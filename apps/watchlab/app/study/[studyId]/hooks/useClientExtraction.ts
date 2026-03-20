/**
 * useClientExtraction — Web Worker lifecycle and TraceRow accumulation.
 *
 * Manages a FaceMesh Web Worker that produces TraceRow[] from webcam frames,
 * eliminating the need for raw JPEG uploads.
 */

import { useRef, useState } from 'react';
import type { TraceRow } from '@/lib/schema';

// ── Types ──────────────────────────────────────────────────────────────────

export type ExtractionStatus = 'idle' | 'initialising' | 'ready' | 'running' | 'error';

type FrameResult = {
  videoTimeMs: number;
  timestampMs: number;
  face_ok: boolean;
  landmarks_ok: boolean;
  eye_openness: number | null;
  blink: 0 | 1;
  au: Record<string, number>;
  au_norm: Record<string, number>;
  head_pose: { yaw: number | null; pitch: number | null; roll: number | null };
  pupil_dilation_proxy: number | null;
};

export interface UseClientExtractionReturn {
  extractionStatus: ExtractionStatus;
  traceRows: TraceRow[];
  frameCount: number;
  initWorker: () => void;
  processFrame: (video: HTMLVideoElement, canvas: HTMLCanvasElement, videoTimeMs: number) => void;
  terminateWorker: () => void;
}

// ── Helpers (exported for testing) ─────────────────────────────────────────

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function buildTraceRow(
  result: FrameResult,
  context: {
    lastVideoTimeMs: number;
    rollingFaceOk: boolean[];
    rollingHeadPoseValid: boolean[];
    rollingBlinks: number[];
  },
): TraceRow {
  const deltaMs = Math.max(1, result.videoTimeMs - context.lastVideoTimeMs);
  const fps = Math.round((1000 / deltaMs) * 100) / 100;

  // Rolling face visible percentage (last 30 frames)
  context.rollingFaceOk.push(result.face_ok);
  if (context.rollingFaceOk.length > 30) context.rollingFaceOk.shift();
  const faceVisiblePct =
    context.rollingFaceOk.filter(Boolean).length / context.rollingFaceOk.length;

  // Rolling head pose valid percentage
  const headPoseValid =
    result.head_pose.yaw !== null &&
    result.head_pose.pitch !== null &&
    result.head_pose.roll !== null;
  context.rollingHeadPoseValid.push(headPoseValid);
  if (context.rollingHeadPoseValid.length > 30) context.rollingHeadPoseValid.shift();
  const headPoseValidPct =
    context.rollingHeadPoseValid.filter(Boolean).length /
    context.rollingHeadPoseValid.length;

  // Rolling blink rate (last 300 frames)
  context.rollingBlinks.push(result.blink);
  if (context.rollingBlinks.length > 300) context.rollingBlinks.shift();
  const rollingBlinkRate =
    context.rollingBlinks.reduce((a, b) => a + b, 0) / context.rollingBlinks.length;

  const blinkBaselineRate = 0.22;
  const blinkInhibitionScore = clamp(
    blinkBaselineRate > 0
      ? (blinkBaselineRate - rollingBlinkRate) / blinkBaselineRate
      : 0,
    -1,
    1,
  );

  return {
    t_ms: result.timestampMs,
    video_time_ms: result.videoTimeMs,
    face_ok: result.face_ok,
    brightness: 128,
    landmarks_ok: result.landmarks_ok,
    blink: result.blink,
    eye_openness: result.eye_openness ?? undefined,
    au: result.au,
    au_norm: result.au_norm,
    head_pose: result.head_pose,
    blur: 0,
    fps: Math.max(0, fps),
    fps_stability: 1.0,
    face_visible_pct: Math.round(faceVisiblePct * 1000000) / 1000000,
    head_pose_valid_pct: Math.round(headPoseValidPct * 1000000) / 1000000,
    occlusion_score: result.eye_openness !== null ? Math.round((1 - result.eye_openness) * 1000000) / 1000000 : 1.0,
    quality_score: result.face_ok ? 0.8 : 0.2,
    quality_confidence: result.face_ok ? 0.8 : 0.1,
    tracking_confidence: result.face_ok ? 0.75 : 0.1,
    quality_flags: [],
    rolling_blink_rate: Math.round(rollingBlinkRate * 1000000) / 1000000,
    blink_baseline_rate: blinkBaselineRate,
    blink_inhibition_score: Math.round(blinkInhibitionScore * 1000000) / 1000000,
    blink_inhibition_active: blinkInhibitionScore > 0.35,
  };
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useClientExtraction(): UseClientExtractionReturn {
  const [extractionStatus, setExtractionStatus] = useState<ExtractionStatus>('idle');
  const [frameCount, setFrameCount] = useState(0);

  const workerRef = useRef<Worker | null>(null);
  const traceRowsRef = useRef<TraceRow[]>([]);
  const lastVideoTimeMsRef = useRef(0);
  const rollingFaceOkRef = useRef<boolean[]>([]);
  const rollingHeadPoseValidRef = useRef<boolean[]>([]);
  const rollingBlinksRef = useRef<number[]>([]);

  const processFrameResult = (result: FrameResult) => {
    const row = buildTraceRow(result, {
      lastVideoTimeMs: lastVideoTimeMsRef.current,
      rollingFaceOk: rollingFaceOkRef.current,
      rollingHeadPoseValid: rollingHeadPoseValidRef.current,
      rollingBlinks: rollingBlinksRef.current,
    });
    lastVideoTimeMsRef.current = result.videoTimeMs;
    traceRowsRef.current.push(row);
    setFrameCount((c) => c + 1);
  };

  const initWorker = () => {
    if (workerRef.current) return;
    try {
      const worker = new Worker('/facemesh-worker.js');
      workerRef.current = worker;
      setExtractionStatus('initialising');

      worker.onmessage = (event: MessageEvent) => {
        const msg = event.data;
        if (msg.type === 'READY') {
          setExtractionStatus('ready');
        } else if (msg.type === 'FRAME_RESULT') {
          processFrameResult(msg as FrameResult);
        } else if (msg.type === 'ERROR') {
          console.error('[useClientExtraction] Worker error:', msg.message);
          setExtractionStatus('error');
        }
      };

      worker.onerror = () => {
        setExtractionStatus('error');
      };

      worker.postMessage({ type: 'INIT' });
    } catch {
      setExtractionStatus('error');
    }
  };

  const processFrame = (
    video: HTMLVideoElement,
    canvas: HTMLCanvasElement,
    videoTimeMs: number,
  ) => {
    if (extractionStatus !== 'ready' && extractionStatus !== 'running') return;
    if (!workerRef.current) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = 224;
    canvas.height = 224;
    ctx.drawImage(video, 0, 0, 224, 224);
    const imageData = ctx.getImageData(0, 0, 224, 224);

    setExtractionStatus('running');
    workerRef.current.postMessage(
      {
        type: 'PROCESS_FRAME',
        imageData,
        videoTimeMs,
        timestampMs: Date.now(),
      },
      [imageData.data.buffer],
    );
  };

  const terminateWorker = () => {
    if (workerRef.current) {
      workerRef.current.terminate();
      workerRef.current = null;
    }
    setExtractionStatus('idle');
  };

  return {
    extractionStatus,
    traceRows: traceRowsRef.current,
    frameCount,
    initWorker,
    processFrame,
    terminateWorker,
  };
}
