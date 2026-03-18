/**
 * useSessionUpload — Upload state and logic extracted from StudyClient.
 *
 * Owns:
 *   State:  uploadStatus, dashboardUrl
 *   Fns:    uploadSession (including retry loop and schema validation)
 */

import { useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import {
  type AnnotationMarker,
  type DialSample,
  type FramePointer,
  type QualitySample,
  type SessionQualitySummary,
  type SessionUploadPayload,
  type SurveyResponse,
  type TimelineEvent,
  type TraceRow,
  type UploadFrame,
  uploadPayloadSchema,
} from '@/lib/schema';
import { detectLowConfidenceWindows } from '@/lib/qualityMetrics';
import { buildCanonicalTraceRows } from '@/lib/traceRows';
import {
  safeUuid,
  collectBrowserMetadata,
  markStudySeen,
  pickUnseenVideo,
  buildStudyHref,
} from '@/lib/studyHelpers';
import type { VideoLibraryItem } from '@/lib/videoLibrary';
import type { StudyStage } from '@/lib/studyTypes';

// ── Types ──────────────────────────────────────────────────────────────────

export interface UseSessionUploadDeps {
  studyId: string;
  participantId: string;
  participantName: string;
  participantEmail: string;
  sessionId: string;
  videoId: string;

  /** Resolve the best source URL for the upload payload. */
  resolveUploadSourceUrl: () => string | undefined;

  // Refs containing collected session data
  timelineRef: MutableRefObject<TimelineEvent[]>;
  framesRef: MutableRefObject<UploadFrame[]>;
  framePointersRef: MutableRefObject<FramePointer[]>;
  dialSamplesRef: MutableRefObject<DialSample[]>;
  qualitySamplesRef: MutableRefObject<QualitySample[]>;
  annotationMarkersRef: MutableRefObject<AnnotationMarker[]>;
  annotationSkippedRef: MutableRefObject<boolean>;

  /** Sample synced video time. */
  sampleSyncedVideoTimeMs: (allowBackward: boolean) => number;
  /** Append a timeline event. */
  appendEvent: (
    type: string,
    details?: Record<string, unknown>,
    allowBackward?: boolean,
    explicitVideoTimeMs?: number,
  ) => void;
  /** Annotation duration for canonical trace row computation. */
  annotationDurationMs: number;
  /** Set the stage after upload. */
  setStage: React.Dispatch<React.SetStateAction<StudyStage>>;
  /** Set the next video choice for sequence playback. */
  setNextVideoChoice: React.Dispatch<
    React.SetStateAction<{ item: VideoLibraryItem; href: string } | null>
  >;
}

export interface UseSessionUploadReturn {
  uploadStatus: string;
  dashboardUrl: string | null;
  uploadTriggeredRef: MutableRefObject<boolean>;
  uploadSession: (surveyResponses: SurveyResponse[]) => Promise<void>;
  setUploadStatus: React.Dispatch<React.SetStateAction<string>>;
  setDashboardUrl: React.Dispatch<React.SetStateAction<string | null>>;
  buildPayload: (surveyResponses: SurveyResponse[]) => SessionUploadPayload;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useSessionUpload(deps: UseSessionUploadDeps): UseSessionUploadReturn {
  const {
    studyId, participantId, participantName, participantEmail,
    sessionId, videoId,
    resolveUploadSourceUrl,
    timelineRef, framesRef, framePointersRef, dialSamplesRef,
    qualitySamplesRef, annotationMarkersRef, annotationSkippedRef,
    sampleSyncedVideoTimeMs, appendEvent,
    annotationDurationMs, setStage, setNextVideoChoice,
  } = deps;

  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [dashboardUrl, setDashboardUrl] = useState<string | null>(null);
  const uploadTriggeredRef = useRef(false);

  // ── Payload builders ──────────────────────────────────────────────────

  const buildSessionQualitySummary = (): SessionQualitySummary => {
    const samples = qualitySamplesRef.current;
    if (samples.length === 0) {
      return {
        sampleCount: 0,
        meanTrackingConfidence: 0,
        meanQualityScore: 0,
        lowConfidenceWindowCount: 0,
        usableSeconds: 0,
      };
    }

    const meanTrackingConfidence =
      samples.reduce((total, s) => total + s.trackingConfidence, 0) / samples.length;
    const meanQualityScore =
      samples.reduce((total, s) => total + s.qualityScore, 0) / samples.length;
    const lowWindows = detectLowConfidenceWindows(samples);
    const durationMs = Math.max(
      ...samples.map((s) => s.videoTimeMs + s.sampleWindowMs),
      0,
    );
    const lowDurationMs = lowWindows.reduce(
      (total, w) => total + Math.max(w.endVideoTimeMs - w.startVideoTimeMs, 0),
      0,
    );
    const usableSeconds = Math.max(durationMs - lowDurationMs, 0) / 1000;

    return {
      sampleCount: samples.length,
      meanTrackingConfidence: Number(meanTrackingConfidence.toFixed(6)),
      meanQualityScore: Number(meanQualityScore.toFixed(6)),
      lowConfidenceWindowCount: lowWindows.length,
      usableSeconds: Number(usableSeconds.toFixed(3)),
    };
  };

  const getCanonicalTraceRows = (): TraceRow[] =>
    buildCanonicalTraceRows({
      dialSamples: dialSamplesRef.current,
      qualitySamples: qualitySamplesRef.current,
      timeline: timelineRef.current,
      annotationDurationMs,
    });

  const buildPayload = (surveyResponses: SurveyResponse[]): SessionUploadPayload => {
    const hasFrames = framesRef.current.length > 0;
    const hasPointers = framePointersRef.current.length > 0;
    const normalizedSourceUrl = resolveUploadSourceUrl();

    if (!hasFrames && !hasPointers) {
      framePointersRef.current.push({
        id: safeUuid(),
        timestampMs: Date.now(),
        videoTimeMs: sampleSyncedVideoTimeMs(false),
        pointer: 'no-webcam-data',
      });
    }

    return {
      studyId,
      videoId,
      sourceUrl: normalizedSourceUrl || undefined,
      participantId,
      participantName: participantName.trim() || undefined,
      participantEmail: participantEmail.trim() || undefined,
      browserMetadata: collectBrowserMetadata(),
      eventTimeline: [...timelineRef.current],
      dialSamples: dialSamplesRef.current,
      traceRows: getCanonicalTraceRows(),
      qualitySamples: qualitySamplesRef.current,
      sessionQualitySummary: buildSessionQualitySummary(),
      annotations: annotationMarkersRef.current,
      annotationSkipped: annotationSkippedRef.current,
      surveyResponses,
      frames: framesRef.current,
      framePointers: framePointersRef.current,
    };
  };

  // ── Upload with retry ─────────────────────────────────────────────────

  const uploadSession = async (surveyResponses: SurveyResponse[]) => {
    let payload: SessionUploadPayload;
    try {
      payload = buildPayload(surveyResponses);
    } catch (buildError) {
      console.error('[uploadSession] Failed to build payload:', buildError);
      setUploadStatus(
        `Upload blocked: ${buildError instanceof Error ? buildError.message : 'Failed to build upload payload.'}`,
      );
      return;
    }

    const validation = uploadPayloadSchema.safeParse(payload);
    if (!validation.success) {
      const issues = validation.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
      console.error('[uploadSession] Schema validation failed:', issues, validation.error.issues);
      setUploadStatus(`Upload blocked: ${issues}`);
      return;
    }

    uploadTriggeredRef.current = true;
    setUploadStatus('Uploading...');
    setDashboardUrl(null);

    const serialized = JSON.stringify(payload);
    const MAX_ATTEMPTS = 3;
    const RETRY_DELAYS_MS = [1000, 3000, 9000];
    let lastError: Error = new Error('Upload failed');

    const attemptUpload = async (attempt: number): Promise<Response> => {
      if (attempt > 1) {
        setUploadStatus(`Saving… retry ${attempt - 1} of ${MAX_ATTEMPTS - 1}`);
        await new Promise<void>((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt - 2]));
      }
      return fetch('/api/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: serialized,
      });
    };

    try {
      let response: Response | null = null;
      for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
        try {
          const r = await attemptUpload(attempt);
          if (!r.ok && r.status >= 500 && attempt < MAX_ATTEMPTS) {
            lastError = new Error(`Upload failed (${r.status})`);
            continue;
          }
          response = r;
          break;
        } catch (networkError) {
          lastError = networkError instanceof Error ? networkError : new Error('Network error');
          if (attempt < MAX_ATTEMPTS) continue;
        }
      }

      if (!response) throw lastError;

      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { error?: string };
        throw new Error(body.error ?? `Upload failed (${response.status})`);
      }

      const body = await response.json();
      const biographVideoId =
        typeof body?.biograph?.videoId === 'string' ? body.biograph.videoId : undefined;
      const dashboardLink =
        typeof body?.biograph?.dashboardUrl === 'string' ? body.biograph.dashboardUrl : null;
      const telemetryWarning =
        typeof body?.biograph?.telemetryWarning === 'string' ? body.biograph.telemetryWarning : null;
      const captureWarning =
        typeof body?.biograph?.captureWarning === 'string' ? body.biograph.captureWarning : null;
      const uploadWarnings = [telemetryWarning, captureWarning].filter(
        (warning): warning is string => typeof warning === 'string' && warning.length > 0,
      );
      const warningSuffix = uploadWarnings.length > 0 ? ` — ${uploadWarnings.join(' — ')}` : '';

      setUploadStatus(
        biographVideoId
          ? `Upload complete: session ${body.sessionId} (video ${biographVideoId})${warningSuffix}`
          : `Upload complete: session ${body.sessionId}${warningSuffix}`,
      );
      setDashboardUrl(dashboardLink);
      appendEvent('upload_success', { uploadedSessionId: body.sessionId });

      const storage = typeof window !== 'undefined' ? window.localStorage : null;
      markStudySeen(storage, studyId);
      const next = pickUnseenVideo(storage, studyId);
      if (next) {
        setNextVideoChoice({ item: next.item, href: buildStudyHref(next.item, next.index) });
        setStage('next_video');
      } else {
        setStage('complete');
      }
    } catch (error) {
      setUploadStatus(
        `Upload failed: ${error instanceof Error ? error.message : 'Unknown server error'}`,
      );
      appendEvent('upload_failed', {
        reason: error instanceof Error ? error.message : 'unknown',
      });
    }
  };

  return {
    uploadStatus, dashboardUrl, uploadTriggeredRef,
    uploadSession, setUploadStatus, setDashboardUrl, buildPayload,
  };
}
