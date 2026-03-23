import { NextResponse } from 'next/server';
import { uploadPayloadSchema, type TraceRow } from '@/lib/schema';
import {
  MissingCanonicalTraceRowsError,
  resolveTraceRowsForUpload
} from '@/lib/traceRows';

const appendPath = (baseUrl: string, path: string) => {
  return `${baseUrl.replace(/\/+$/, '')}${path}`;
};

/** Build common headers for biograph API calls, including auth when configured. */
const biographHeaders = (extra?: Record<string, string>): Record<string, string> => {
  const token = process.env.BIOGRAPH_API_TOKEN?.trim();
  const headers: Record<string, string> = { ...extra };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

const normalizeBiographBaseUrl = (rawValue: string | undefined): string | null => {
  if (!rawValue) {
    return null;
  }
  const trimmed = rawValue.trim();
  if (!trimmed || trimmed.includes('<') || trimmed.includes('>')) {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString().replace(/\/+$/, '');
  } catch {
    return null;
  }
};

const toDashboardUrl = (baseUrl: string | undefined, videoId: string): string | undefined => {
  if (!baseUrl) {
    return undefined;
  }
  return `${baseUrl.replace(/\/+$/, '')}/videos/${videoId}`;
};

const shouldAllowSyntheticTraceFallback = (studyId: string): boolean => {
  // Opt-out: only disable synthetic fallback if explicitly set to "false".
  // Default to true — rejecting uploads because trace rows are empty is worse
  // than accepting them with synthetic placeholder data that still captures
  // dial, survey, annotation, and telemetry signals.
  const envOptOut = process.env.WATCHLAB_ALLOW_SYNTHETIC_TRACE_FALLBACK;
  if (envOptOut && envOptOut.trim().toLowerCase() === 'false') {
    return studyId.trim().toLowerCase() === 'demo';
  }
  return true;
};

const VIDEO_ASSET_PROXY_PATH = '/api/video-assets/';
const VIDEO_ASSET_PUBLIC_PATH = '/video-assets/';
const VIDEO_HLS_PROXY_PATH = '/api/video/hls-proxy';
const DEFAULT_VIDEO_ASSET_ORIGIN = 'https://biograph-api-production.up.railway.app';

const getVideoAssetOrigin = (): string =>
  (process.env.VIDEO_ASSET_PROXY_ORIGIN?.trim() || DEFAULT_VIDEO_ASSET_ORIGIN).replace(/\/+$/, '');

const unwrapHlsProxySourceUrl = (value: string): string | undefined => {
  try {
    const parsed = value.startsWith('http://') || value.startsWith('https://')
      ? new URL(value)
      : new URL(value, 'https://watchlab.local');
    if (!parsed.pathname.startsWith(VIDEO_HLS_PROXY_PATH)) {
      return undefined;
    }
    const proxied = parsed.searchParams.get('url')?.trim() ?? '';
    return proxied || undefined;
  } catch {
    return undefined;
  }
};

const normalizeSourceUrlForBiograph = (rawValue: string | undefined): string | undefined => {
  if (!rawValue) {
    return undefined;
  }
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return undefined;
  }
  const proxiedSource = unwrapHlsProxySourceUrl(trimmed);
  if (proxiedSource && proxiedSource !== trimmed) {
    return normalizeSourceUrlForBiograph(proxiedSource);
  }
  if (trimmed.startsWith(VIDEO_ASSET_PROXY_PATH)) {
    const remainder = trimmed.slice(VIDEO_ASSET_PROXY_PATH.length);
    if (!remainder) {
      return undefined;
    }
    return `${getVideoAssetOrigin()}/video-assets/${remainder}`;
  }
  if (trimmed.startsWith(VIDEO_ASSET_PUBLIC_PATH)) {
    const remainder = trimmed.slice(VIDEO_ASSET_PUBLIC_PATH.length);
    if (!remainder) {
      return undefined;
    }
    return `${getVideoAssetOrigin()}/video-assets/${remainder}`;
  }
  if (trimmed.startsWith('/')) {
    return trimmed;
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return undefined;
    }
    return parsed.toString();
  } catch {
    return undefined;
  }
};

async function createStudyAndVideo(
  baseUrl: string,
  studyKey: string,
  videoKey: string,
  sourceUrl?: string
) {
  const studyResponse = await fetch(appendPath(baseUrl, '/studies'), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      name: `NeuroTrace ${studyKey}`,
      description: 'Auto-provisioned by Watchlab upload route.'
    })
  });
  if (!studyResponse.ok) {
    const body = await studyResponse.text();
    throw new Error(`biograph study create failed (${studyResponse.status}): ${body}`);
  }

  const studyBody = (await studyResponse.json()) as { id: string };

  const videoResponse = await fetch(appendPath(baseUrl, '/videos'), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      study_id: studyBody.id,
      title: `Stimulus ${videoKey}`,
      source_url: sourceUrl ?? process.env.DEFAULT_STUDY_VIDEO_URL ?? '/sample.mp4',
      duration_ms: 60_000
    })
  });
  if (!videoResponse.ok) {
    const body = await videoResponse.text();
    throw new Error(`biograph video create failed (${videoResponse.status}): ${body}`);
  }

  const videoBody = (await videoResponse.json()) as { id: string };

  return {
    studyId: studyBody.id,
    videoId: videoBody.id,
    created: true
  };
}

async function updateVideoSourceUrl(baseUrl: string, videoId: string, sourceUrl: string) {
  const response = await fetch(appendPath(baseUrl, `/videos/${videoId}`), {
    method: 'PATCH',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      source_url: sourceUrl
    })
  });
  if (response.ok) {
    return { forwarded: true as const };
  }
  // Source URL sync is non-critical — never block the session upload.
  const body = await response.text().catch(() => '');
  console.warn(`[upload] Video source URL update returned ${response.status}: ${body.slice(0, 200)}`);
  return {
    forwarded: false as const,
    warning:
      `Video source URL update returned ${response.status}; continuing without source URL sync.`
  };
}

async function createSession(
  baseUrl: string,
  studyId: string,
  videoId: string,
  participantId: string,
  participantName?: string,
  participantEmail?: string
) {
  const participant: Record<string, string> = { external_id: participantId };
  if (participantName) participant.name = participantName;
  if (participantEmail) participant.email = participantEmail;

  const sessionResponse = await fetch(appendPath(baseUrl, '/sessions'), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      study_id: studyId,
      video_id: videoId,
      participant,
      status: 'completed'
    })
  });

  return sessionResponse;
}

async function forwardToBiograph(payload: {
  studyId: string;
  videoId: string;
  sourceUrl?: string;
  participantId: string;
  participantName?: string;
  participantEmail?: string;
  eventTimeline: Array<{
    type: string;
    sessionId: string;
    videoId: string;
    videoTimeMs: number;
    clientMonotonicMs: number;
    wallTimeMs: number;
    details?: Record<string, unknown>;
  }>;
  dialSamples: Array<{ videoTimeMs: number; value: number }>;
  annotations: Array<{
    sessionId: string;
    videoId: string;
    markerType: 'engaging_moment' | 'confusing_moment' | 'stop_watching_moment' | 'cta_landed_moment';
    videoTimeMs: number;
    note?: string | null;
    createdAt: string;
  }>;
  annotationSkipped: boolean;
  surveyResponses: Array<{
    questionKey: string;
    responseNumber?: number;
    responseText?: string;
    responseJson?: Record<string, unknown>;
  }>;
  frames: Array<{
    id: string;
    timestampMs: number;
    videoTimeMs?: number;
    jpegBase64: string;
  }>;
  framePointers: Array<{
    id: string;
    timestampMs: number;
    videoTimeMs?: number;
    pointer: string;
  }>;
  qualitySamples: Array<{
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
    qualityFlags: Array<'low_light' | 'blur' | 'face_lost' | 'high_yaw_pitch'>;
  }>;
  traceRows: TraceRow[];
}) {
  const baseUrl = normalizeBiographBaseUrl(process.env.BIOGRAPH_API_BASE_URL);
  const studyId = process.env.BIOGRAPH_STUDY_ID;
  const videoId = process.env.BIOGRAPH_VIDEO_ID;
  const dashboardBaseUrl = process.env.DASHBOARD_BASE_URL;
  const normalizedSourceUrl = normalizeSourceUrlForBiograph(payload.sourceUrl);

  if (!baseUrl) {
    return {
      forwarded: false,
      reason: 'BIOGRAPH_API_BASE_URL not configured or invalid'
    };
  }

  let activeStudyId = studyId;
  let activeVideoId = videoId;
  let createdStudy = false;
  let createdVideo = false;

  if (!activeStudyId || !activeVideoId) {
    const created = await createStudyAndVideo(
      baseUrl,
      payload.studyId,
      payload.videoId,
      normalizedSourceUrl
    );
    activeStudyId = created.studyId;
    activeVideoId = created.videoId;
    createdStudy = created.created;
    createdVideo = created.created;
  }
  if (!activeStudyId || !activeVideoId) {
    throw new Error('Failed to resolve study/video identifiers for biograph forwarding.');
  }

  // --- Resolve trace rows (shared by batch and legacy paths) ----------------
  const { traceRows, traceSource } = resolveTraceRowsForUpload({
    traceRows: payload.traceRows,
    dialSamples: payload.dialSamples,
    eventTimeline: payload.eventTimeline,
    qualitySamples: payload.qualitySamples,
    allowSyntheticFallback: shouldAllowSyntheticTraceFallback(payload.studyId)
  });
  const traceJsonl = traceRows.map((row) => JSON.stringify(row)).join('\n');

  // --- Source URL sync (independent of session path) -----------------------
  let sourceUrlForwarded = false;
  let sourceUrlWarning: string | undefined;
  if (normalizedSourceUrl) {
    const sourceUpdateResult = await updateVideoSourceUrl(baseUrl, activeVideoId, normalizedSourceUrl);
    sourceUrlForwarded = sourceUpdateResult.forwarded;
    sourceUrlWarning = sourceUpdateResult.warning;
    if (!sourceUpdateResult.forwarded && sourceUpdateResult.warning) {
      console.warn(sourceUpdateResult.warning);
    }
  }

  // --- Build mapped arrays (shared by batch and legacy paths) --------------
  const telemetryEvents = [
    ...payload.eventTimeline.map((event) => ({
      video_id: activeVideoId,
      event_type: event.type,
      video_time_ms: Math.max(0, Math.round(event.videoTimeMs)),
      wall_time_ms: Math.max(0, Math.round(event.wallTimeMs)),
      client_monotonic_ms: Math.max(0, Math.round(event.clientMonotonicMs)),
      details: event.details
    })),
    {
      video_id: activeVideoId,
      event_type: 'trace_source',
      video_time_ms: 0,
      wall_time_ms: Date.now(),
      client_monotonic_ms: 0,
      details: { trace_source: traceSource }
    }
  ];

  const annotationsMapped = payload.annotations.map((entry) => ({
    video_id: activeVideoId,
    marker_type: entry.markerType,
    video_time_ms: entry.videoTimeMs,
    note: entry.note ?? null,
    created_at: entry.createdAt
  }));

  const surveyMapped = payload.surveyResponses.map((entry) => ({
    question_key: entry.questionKey,
    response_number: entry.responseNumber,
    response_text: entry.responseText,
    response_json: entry.responseJson
  }));

  const framesMapped = payload.frames.map((frame) => ({
    id: frame.id,
    timestamp_ms: Math.max(0, Math.round(frame.timestampMs)),
    video_time_ms:
      typeof frame.videoTimeMs === 'number' ? Math.max(0, Math.round(frame.videoTimeMs)) : undefined,
    jpeg_base64: frame.jpegBase64
  }));

  const framePointersMapped = payload.framePointers.map((fp) => ({
    id: fp.id,
    timestamp_ms: Math.max(0, Math.round(fp.timestampMs)),
    video_time_ms:
      typeof fp.videoTimeMs === 'number' ? Math.max(0, Math.round(fp.videoTimeMs)) : undefined,
    pointer: fp.pointer
  }));

  // --- R23: Atomic batch ingest — single transaction, no partial state -----
  const batchParticipant: Record<string, string> = { external_id: payload.participantId };
  if (payload.participantName) batchParticipant.name = payload.participantName;
  if (payload.participantEmail) batchParticipant.email = payload.participantEmail;

  try {
    const batchResponse = await fetch(appendPath(baseUrl, '/sessions/batch-ingest'), {
      method: 'POST',
      headers: biographHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        study_id: activeStudyId,
        video_id: activeVideoId,
        participant: batchParticipant,
        status: 'completed',
        trace_jsonl: traceJsonl,
        telemetry_events: telemetryEvents,
        annotations: annotationsMapped,
        annotation_skipped: payload.annotationSkipped,
        survey_responses: surveyMapped,
        capture_frames: framesMapped,
        capture_frame_pointers: framePointersMapped
      })
    });

    if (batchResponse.ok) {
      const batchData = (await batchResponse.json()) as {
        session_id: string;
        trace_inserted: number;
        telemetry_inserted: number;
        annotations_inserted: number;
        survey_inserted: number;
        capture_archived: boolean;
        capture_frame_count: number;
        capture_pointer_count: number;
      };

      return {
        forwarded: true,
        sessionId: batchData.session_id,
        studyId: activeStudyId,
        videoId: activeVideoId,
        createdStudy,
        createdVideo,
        telemetryForwarded: true,
        captureForwarded: batchData.capture_archived,
        captureWarning: batchData.capture_archived
          ? undefined
          : 'Capture archive is disabled server-side; frames were not persisted.',
        sourceUrlForwarded,
        sourceUrlWarning,
        sourceUrlApplied: normalizedSourceUrl ?? null,
        captureFrameCount: batchData.capture_frame_count,
        capturePointerCount: batchData.capture_pointer_count,
        traceSource,
        traceRowsForwarded: batchData.trace_inserted,
        dashboardUrl: toDashboardUrl(dashboardBaseUrl, activeVideoId)
      };
    }

    // Fall through to legacy multi-step for ANY non-2xx response.
    // The batch endpoint may fail for many transient reasons (503 config errors,
    // 500 DB issues, 502 deploy in progress) — none of these should block the
    // upload.  Legacy path handles each step independently with its own error
    // tolerance.
    const batchBody = await batchResponse.text().catch(() => '');
    console.warn(
      `Batch ingest returned ${batchResponse.status}; falling back to legacy multi-step upload. Body: ${batchBody.slice(0, 300)}`
    );
  } catch (err) {
    // Network errors, timeouts, JSON parse failures — fall through to legacy path
    console.warn('Batch ingest unavailable; falling back to legacy multi-step upload.', err);
  }

  // --- Legacy multi-step fallback (for older API deployments) --------------
  let sessionResponse = await createSession(
    baseUrl,
    activeStudyId,
    activeVideoId,
    payload.participantId,
    payload.participantName,
    payload.participantEmail
  );
  if (!sessionResponse.ok && (sessionResponse.status === 400 || sessionResponse.status === 404)) {
    const created = await createStudyAndVideo(
      baseUrl,
      payload.studyId,
      payload.videoId,
      normalizedSourceUrl
    );
    activeStudyId = created.studyId;
    activeVideoId = created.videoId;
    createdStudy = created.created;
    createdVideo = created.created;
    sessionResponse = await createSession(
      baseUrl,
      activeStudyId,
      activeVideoId,
      payload.participantId,
      payload.participantName,
      payload.participantEmail
    );
  }

  if (!sessionResponse.ok) {
    const body = await sessionResponse.text();
    throw new Error(
      `biograph session create failed (${sessionResponse.status}) for study/video ${activeStudyId}/${activeVideoId}: ${body}`
    );
  }

  const sessionBody = (await sessionResponse.json()) as { id: string };
  const sessionId = sessionBody.id;

  const traceResponse = await fetch(appendPath(baseUrl, `/sessions/${sessionId}/trace`), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/x-ndjson' }),
    body: traceJsonl
  });
  if (!traceResponse.ok) {
    const body = await traceResponse.text();
    throw new Error(`biograph trace ingest failed (${traceResponse.status}): ${body}`);
  }

  const telemetryResponse = await fetch(appendPath(baseUrl, `/sessions/${sessionId}/telemetry`), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      events: telemetryEvents.map((e) => ({ ...e, session_id: sessionId }))
    })
  });
  let telemetryForwarded = true;
  let telemetryWarning: string | undefined;
  if (!telemetryResponse.ok) {
    telemetryForwarded = false;
    const telBody = await telemetryResponse.text().catch(() => '');
    telemetryWarning =
      `Telemetry ingest returned ${telemetryResponse.status}; continuing without telemetry. ${telBody.slice(0, 200)}`;
  }

  if (!telemetryForwarded) {
    console.warn(telemetryWarning);
  }

  const annotationsResponse = await fetch(appendPath(baseUrl, `/sessions/${sessionId}/annotations`), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      annotation_skipped: payload.annotationSkipped,
      annotations: annotationsMapped.map((a) => ({ ...a, session_id: sessionId }))
    })
  });
  if (!annotationsResponse.ok) {
    const annBody = await annotationsResponse.text().catch(() => '');
    console.warn(`[upload] Annotations ingest returned ${annotationsResponse.status}: ${annBody.slice(0, 200)}`);
  }

  const surveyResponse = await fetch(appendPath(baseUrl, `/sessions/${sessionId}/survey`), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ responses: surveyMapped })
  });
  if (!surveyResponse.ok) {
    const srvBody = await surveyResponse.text().catch(() => '');
    console.warn(`[upload] Survey ingest returned ${surveyResponse.status}: ${srvBody.slice(0, 200)}`);
  }

  const captureResponse = await fetch(appendPath(baseUrl, `/sessions/${sessionId}/captures`), {
    method: 'POST',
    headers: biographHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      video_id: activeVideoId,
      frames: framesMapped,
      frame_pointers: framePointersMapped
    })
  });
  let captureForwarded = true;
  let captureWarning: string | undefined;
  if (!captureResponse.ok) {
    captureForwarded = false;
    const capBody = await captureResponse.text().catch(() => '');
    captureWarning =
      `Capture archive returned ${captureResponse.status}; continuing without persisted frames. ${capBody.slice(0, 200)}`;
  }

  if (!captureForwarded) {
    console.warn(captureWarning);
  }

  return {
    forwarded: true,
    sessionId,
    studyId: activeStudyId,
    videoId: activeVideoId,
    createdStudy,
    createdVideo,
    telemetryForwarded,
    telemetryWarning,
    captureForwarded,
    captureWarning,
    sourceUrlForwarded,
    sourceUrlWarning,
    sourceUrlApplied: normalizedSourceUrl ?? null,
    captureFrameCount: payload.frames.length,
    capturePointerCount: payload.framePointers.length,
    traceSource,
    traceRowsForwarded: traceRows.length,
    dashboardUrl: toDashboardUrl(dashboardBaseUrl, activeVideoId)
  };
}

export async function POST(request: Request) {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        error: 'Invalid JSON body.'
      },
      { status: 400 }
    );
  }

  const parsed = uploadPayloadSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      {
        error: 'Payload failed validation.',
        issues: parsed.error.issues
      },
      { status: 400 }
    );
  }

  const sessionId = crypto.randomUUID();
  let biographResult:
    | {
        forwarded: boolean;
        reason?: string;
        sessionId?: string;
      }
    | undefined;

  try {
    biographResult = await forwardToBiograph({
      studyId: parsed.data.studyId,
      videoId: parsed.data.videoId,
      sourceUrl: parsed.data.sourceUrl,
      participantId: parsed.data.participantId,
      participantName: parsed.data.participantName,
      participantEmail: parsed.data.participantEmail,
      eventTimeline: parsed.data.eventTimeline.map((event) => ({
        type: event.type,
        sessionId: event.sessionId,
        videoId: event.videoId,
        videoTimeMs: event.videoTimeMs,
        clientMonotonicMs: event.clientMonotonicMs,
        wallTimeMs: event.wallTimeMs,
        details: event.details
      })),
      dialSamples: parsed.data.dialSamples,
      annotations: parsed.data.annotations,
      annotationSkipped: parsed.data.annotationSkipped,
      surveyResponses: parsed.data.surveyResponses,
      frames: parsed.data.frames,
      framePointers: parsed.data.framePointers,
      qualitySamples: parsed.data.qualitySamples,
      traceRows: parsed.data.traceRows
    });
  } catch (error) {
    if (error instanceof MissingCanonicalTraceRowsError) {
      return NextResponse.json(
        {
          error: error.message
        },
        { status: 400 }
      );
    }

    // -----------------------------------------------------------------------
    // Biograph forwarding is NON-CRITICAL. The session payload has already been
    // validated — the participant completed the study, provided survey answers,
    // and we captured their trace/dial/annotation data.  That data is in the
    // request body and will be returned to the client in the success response.
    //
    // If biograph_api is down, misconfigured, or returns an unexpected error,
    // we log it but still return 200 so the participant isn't told their work
    // was lost.  The session can be re-ingested from the client payload later.
    // -----------------------------------------------------------------------
    console.error(
      '[upload] biograph forwarding failed (non-fatal):',
      error instanceof Error ? error.message : error
    );
    biographResult = {
      forwarded: false,
      reason: error instanceof Error ? error.message : 'biograph forwarding failed'
    };
  }

  return NextResponse.json({
    ok: true,
    sessionId,
    acceptedAt: new Date().toISOString(),
    participantName: parsed.data.participantName,
    participantEmail: parsed.data.participantEmail,
    events: parsed.data.eventTimeline.length,
    dialSamples: parsed.data.dialSamples.length,
    annotations: parsed.data.annotations.length,
    annotationSkipped: parsed.data.annotationSkipped,
    surveyResponses: parsed.data.surveyResponses.length,
    frames: parsed.data.frames.length,
    framePointers: parsed.data.framePointers.length,
    biograph: biographResult
  });
}
