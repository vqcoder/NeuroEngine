'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AnnotationMarker,
  DialSample,
  FramePointer,
  QualitySample,
  SessionQualitySummary,
  SessionUploadPayload,
  SurveyResponse,
  TimelineEvent,
  TraceRow,
  UploadFrame,
  uploadPayloadSchema
} from '@/lib/schema';
import { VideoTimeTracker } from '@/lib/videoClock';
import {
  brightnessScore,
  blurScore,
  computeFpsStability,
  computeQualityScore,
  computeTrackingConfidence,
  detectLowConfidenceWindows,
  detectQualityFlags
} from '@/lib/qualityMetrics';
import {
  WATCHLAB_LIBRARY_ID,
  buildStudyHref,
  isHttpUrl,
  readVideoLibrary,
  writeVideoLibrary,
  type VideoLibraryItem
} from '@/lib/videoLibrary';
import {
  type StudyConfig,
  type FrontendDiagnosticSeverity,
  type StudyStage,
  type WebcamStatus,
  type BrowserFaceDetectionResult,
  type QualityState,
  type FrameCounterState,
  type MarkerType,
  type SurveyAnalyticsHighlightCategory,
  type SurveyAnalyticsHighlight,
  markerTypes,
  markerLabels,
  defaultTraceAu,
  QUALITY_SAMPLE_INTERVAL_MS,
  QUALITY_SAMPLE_WINDOW_MS,
  TRACE_DEFAULT_BLINK_BASELINE_RATE,
  clampNumber,
  DEFAULT_QUALITY,
  MAX_STORED_FRAMES,
  emptyConfig
} from '@/lib/studyTypes';
import {
  saveParticipantInfo,
  readParticipantInfo,
  readSeenStudyIds,
  markStudySeen,
  pickUnseenVideo,
  safeUuid,
  maybeUuid,
  parseSurveyScore,
  parseSequenceIndex,
  parseEntryId,
  isPlaybackTelemetryStage,
  collectBrowserMetadata,
  applyCanonicalLibraryParams,
  looksLikeWebPageUrl,
  unwrapHlsProxySourceUrl,
  looksLikeHlsUrl,
  toHlsProxyUrl,
  getDefaultStudyFallbackUrl,
  isGithubHostedVideoUrl,
  mapToProxyAssetUrl,
  normalizeLegacyAssetUrl,
  VIDEO_ASSET_PROXY_PATH,
  VIDEO_HLS_PROXY_PATH,
  VIDEO_ASSET_FILENAME_PATTERN,
  LEGACY_VIDEO_ASSET_ORIGIN
} from '@/lib/studyHelpers';
import { buildSurveyAnalyticsHighlights } from '@/lib/surveyAnalytics';
import { buildCanonicalTraceRows } from '@/lib/traceRows';
import StudyOnboarding from './components/StudyOnboarding';
import StudyCameraCheck from './components/StudyCameraCheck';
import StudyAnnotation from './components/StudyAnnotation';
import StudySurvey from './components/StudySurvey';
import StudyCompletion from './components/StudyCompletion';


export default function StudyClient({ studyId }: { studyId: string }) {
  const [consented, setConsented] = useState(false);
  const [stage, setStage] = useState<StudyStage>('onboarding');
  const [config, setConfig] = useState<StudyConfig>(emptyConfig);
  const [configError, setConfigError] = useState<string | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [isReturningParticipant] = useState(() =>
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('returning') === '1'
      : false
  );

  const [participantId] = useState(() => safeUuid());
  const [sessionId] = useState(() => safeUuid());
  const [participantName, setParticipantName] = useState('');
  const [participantEmail, setParticipantEmail] = useState('');
  const [webcamStatus, setWebcamStatus] = useState<WebcamStatus>('idle');
  const [webcamBypassed, setWebcamBypassed] = useState(false);
  const [quality, setQuality] = useState<QualityState>(DEFAULT_QUALITY);
  const [capturedFrameCount, setCapturedFrameCount] = useState(0);

  const [videoTimeMs, setVideoTimeMs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [videoCompleted, setVideoCompleted] = useState(false);
  const [firstPassEnded, setFirstPassEnded] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [dashboardUrl, setDashboardUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [nextStudyHref, setNextStudyHref] = useState<string | null>(null);
  const [nextStudyTitle, setNextStudyTitle] = useState<string | null>(null);
  const [nextVideoChoice, setNextVideoChoice] = useState<{ item: VideoLibraryItem; href: string } | null>(null);

  const [dialModeEnabled, setDialModeEnabled] = useState(false);
  const [dialValue, setDialValue] = useState(50);
  const [dialSampleCount, setDialSampleCount] = useState(0);

  const [audioCheckPlayed, setAudioCheckPlayed] = useState(false);
  const [audioConfirmed, setAudioConfirmed] = useState(false);

  const [annotationMarkers, setAnnotationMarkers] = useState<AnnotationMarker[]>([]);
  const [annotationSkipped, setAnnotationSkipped] = useState(false);
  const [annotationNoteDraft, setAnnotationNoteDraft] = useState('');
  const [annotationCursorMs, setAnnotationCursorMs] = useState(0);
  const [annotationDurationMs, setAnnotationDurationMs] = useState(0);

  const [surveyOverallEngagement, setSurveyOverallEngagement] = useState('');
  const [surveyContentClarity, setSurveyContentClarity] = useState('');
  const [surveyAdditionalComments, setSurveyAdditionalComments] = useState('');

  const studyVideoRef = useRef<HTMLVideoElement | null>(null);
  const webcamVideoRef = useRef<HTMLVideoElement | null>(null);
  const qualityCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const qualityLoopTimerRef = useRef<number | null>(null);
  const frameCaptureTimerRef = useRef<number | null>(null);
  const dialSampleTimerRef = useRef<number | null>(null);
  const dialValueRef = useRef(dialValue);

  const frameCounterRef = useRef<FrameCounterState>({
    active: false,
    frames: 0,
    lastSampleMs: 0,
    fps: 0,
    sampleTimerId: null,
    callbackHandle: null,
    callbackMode: null
  });

  const faceDetectorRef = useRef<{
    detect: (input: HTMLVideoElement) => Promise<BrowserFaceDetectionResult[]>;
  } | null>(null);
  const framesRef = useRef<UploadFrame[]>([]);
  const framePointersRef = useRef<FramePointer[]>([]);
  const dialSamplesRef = useRef<DialSample[]>([]);
  const qualitySamplesRef = useRef<QualitySample[]>([]);
  const qualityCheckInFlightRef = useRef(false);
  const recentFpsRef = useRef<number[]>([]);
  const recentFaceVisibleRef = useRef<boolean[]>([]);
  const recentHeadPoseValidRef = useRef<boolean[]>([]);
  const timelineRef = useRef<TimelineEvent[]>([]);
  const annotationMarkersRef = useRef<AnnotationMarker[]>([]);
  const annotationSkippedRef = useRef(false);

  const videoTimeTrackerRef = useRef(new VideoTimeTracker());
  const monotonicClientTimeRef = useRef(0);
  const lastObservedVideoTimeRef = useRef(0);
  const isMutedRef = useRef(false);
  const lastVolumeRef = useRef(1);
  const seekStartVideoTimeRef = useRef<number | null>(null);
  const stageRef = useRef<StudyStage>('onboarding');
  const uploadTriggeredRef = useRef(false);
  const hlsPlayerRef = useRef<{ destroy: () => void } | null>(null);
  const hlsSourceBoundRef = useRef<string | null>(null);
  const cloudHostingInFlightRef = useRef(false);
  const cloudHostingAttemptedRef = useRef(new Set<string>());
  const hlsRecoveryAttemptedRef = useRef(new Map<string, number>());
  const diagnosticDedupeRef = useRef(new Set<string>());
  const defaultStudyFallbackUrl = getDefaultStudyFallbackUrl(studyId);
  const isDefaultStudyWithPinnedFallback =
    Boolean(defaultStudyFallbackUrl) && !looksLikeHlsUrl(defaultStudyFallbackUrl ?? '');

  const reportDiagnostic = ({
    eventType,
    severity = 'error',
    errorCode,
    message,
    context,
    dedupeKey
  }: {
    eventType: string;
    severity?: FrontendDiagnosticSeverity;
    errorCode?: string;
    message?: string;
    context?: Record<string, unknown>;
    dedupeKey?: string;
  }) => {
    const dedupe = dedupeKey?.trim();
    if (dedupe) {
      if (diagnosticDedupeRef.current.has(dedupe)) {
        return;
      }
      diagnosticDedupeRef.current.add(dedupe);
    }

    const route =
      typeof window !== 'undefined'
        ? `${window.location.pathname}${window.location.search}`
        : `/study/${studyId}`;

    const payload = {
      surface: 'watchlab',
      page: 'study',
      route,
      severity,
      event_type: eventType,
      ...(errorCode ? { error_code: errorCode } : {}),
      ...(message ? { message } : {}),
      ...(maybeUuid(sessionId) ? { session_id: maybeUuid(sessionId) } : {}),
      ...(maybeUuid(config.videoId) ? { video_id: maybeUuid(config.videoId) } : {}),
      study_id: studyId,
      context: {
        configured_video_id: config.videoId,
        configured_video_url: config.videoUrl,
        original_video_url: config.originalVideoUrl ?? null,
        stage: stageRef.current,
        ...(context ?? {})
      }
    };

    void fetch('/api/diagnostics/frontend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).catch(() => undefined);
  };

  useEffect(() => {
    stageRef.current = stage;
  }, [stage]);


  useEffect(() => {
    dialValueRef.current = dialValue;
  }, [dialValue]);

  useEffect(() => {
    annotationMarkersRef.current = annotationMarkers;
  }, [annotationMarkers]);

  useEffect(() => {
    annotationSkippedRef.current = annotationSkipped;
  }, [annotationSkipped]);

  const destroyHlsPlayer = () => {
    if (hlsPlayerRef.current) {
      hlsPlayerRef.current.destroy();
      hlsPlayerRef.current = null;
    }
    hlsSourceBoundRef.current = null;
  };


  const persistHostedLibraryVideo = (hostedUrl: string, sourceUrl: string) => {
    if (typeof window === 'undefined') {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get('library') !== WATCHLAB_LIBRARY_ID) {
      return;
    }
    const storage = window.localStorage;
    const items = readVideoLibrary(storage);
    const entryId = params.get('entry_id');
    const targetStudyId = params.get('video_id') || studyId;
    const itemIndex =
      entryId
        ? items.findIndex((item) => item.id === entryId)
        : items.findIndex((item) => item.studyId === targetStudyId);
    if (itemIndex < 0) {
      return;
    }

    const current = items[itemIndex];
    const originalUrl = current.originalUrl ?? (isHttpUrl(sourceUrl) ? sourceUrl : undefined);
    const nextItem: VideoLibraryItem = {
      ...current,
      videoUrl: hostedUrl,
      ...(originalUrl ? { originalUrl } : {})
    };
    items[itemIndex] = nextItem;
    writeVideoLibrary(storage, items);
  };

  const hostVideoInCloud = async (
    sourceUrlRaw: string,
    options?: { silent?: boolean }
  ): Promise<string | null> => {
    const sourceUrl = sourceUrlRaw.trim();
    const proxiedUrl = mapToProxyAssetUrl(sourceUrl);
    if (proxiedUrl && proxiedUrl !== sourceUrl) {
      setConfig((prev) => ({
        ...prev,
        videoUrl: proxiedUrl,
        originalVideoUrl: prev.originalVideoUrl ?? (isHttpUrl(sourceUrl) ? sourceUrl : prev.originalVideoUrl)
      }));
      persistHostedLibraryVideo(proxiedUrl, sourceUrl);
      return proxiedUrl;
    }
    if (!isHttpUrl(sourceUrl) || isGithubHostedVideoUrl(sourceUrl)) {
      return null;
    }
    if (cloudHostingAttemptedRef.current.has(sourceUrl) || cloudHostingInFlightRef.current) {
      return null;
    }

    cloudHostingAttemptedRef.current.add(sourceUrl);
    cloudHostingInFlightRef.current = true;
    try {
      const response = await fetch('/api/video/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: sourceUrl,
          title: config.title
        })
      });
      const body = (await response.json().catch(() => null)) as
        | { videoUrl?: string; error?: string }
        | null;
      if (!response.ok) {
        throw new Error(body?.error ?? `Cloud hosting failed (${response.status}).`);
      }
      const hostedUrl = body?.videoUrl?.trim() ?? '';
      if (!hostedUrl) {
        throw new Error('Cloud hosting did not return a URL.');
      }

      setConfig((prev) => ({
        ...prev,
        videoUrl: hostedUrl,
        originalVideoUrl: prev.originalVideoUrl ?? sourceUrl
      }));
      persistHostedLibraryVideo(hostedUrl, sourceUrl);
      return hostedUrl;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Cloud hosting failed for this source URL.';
      if (!options?.silent) {
        setVideoError(`Video playback failed: ${message}`);
        reportDiagnostic({
          eventType: 'study_cloud_hosting_failed',
          severity: 'error',
          errorCode: 'cloud_host_failed',
          message,
          context: {
            source_url: sourceUrl
          },
          dedupeKey: `study_cloud_hosting_failed:${sourceUrl}:${message}`
        });
      }
      return null;
    } finally {
      cloudHostingInFlightRef.current = false;
    }
  };


  const resolveUploadSourceUrl = (): string | undefined => {
    const candidates = [
      config.videoUrl,
      config.originalVideoUrl ?? '',
      defaultStudyFallbackUrl ?? ''
    ]
      .map((value) => normalizeLegacyAssetUrl(value.trim()))
      .filter((value, index, list) => value.length > 0 && list.indexOf(value) === index);

    if (candidates.length === 0) {
      return undefined;
    }
    const nonHls = candidates.find((value) => !looksLikeHlsUrl(value));
    return nonHls ?? candidates[0];
  };

  const pickRecoverySource = (...rawCandidates: Array<string | null | undefined>): string => {
    const candidates = rawCandidates
      .map((value) => value?.trim() ?? '')
      .filter((value, index, array) => value.length > 0 && array.indexOf(value) === index);
    if (candidates.length === 0) {
      return '';
    }
    const nonHlsCandidate = candidates.find((value) => !looksLikeHlsUrl(value));
    if (isDefaultStudyWithPinnedFallback && defaultStudyFallbackUrl) {
      return nonHlsCandidate ?? defaultStudyFallbackUrl;
    }
    return nonHlsCandidate ?? candidates[0];
  };

  const getSourceCandidates = (sourceUrl: string): string[] => {
    const trimmed = sourceUrl.trim();
    const candidates = [trimmed];
    const legacy = normalizeLegacyAssetUrl(trimmed);
    if (legacy !== trimmed) {
      candidates.push(legacy);
    }
    if (trimmed !== '/sample.mp4') {
      candidates.push('/sample.mp4');
    }

    return [...new Set(candidates.filter((value) => value.length > 0))];
  };

  const tryLoadVideoSource = async (video: HTMLVideoElement, sourceUrl: string): Promise<boolean> => {
    if ((video.currentSrc || video.src) !== sourceUrl) {
      video.src = sourceUrl;
    }
    video.load();

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      return true;
    }

    return await new Promise<boolean>((resolve) => {
      let settled = false;
      const onLoadedMetadata = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(true);
      };
      const onCanPlay = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(true);
      };
      const onError = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(false);
      };
      const timeoutId = window.setTimeout(() => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(false);
      }, 7000);

      const cleanup = () => {
        window.clearTimeout(timeoutId);
        video.removeEventListener('loadedmetadata', onLoadedMetadata);
        video.removeEventListener('canplay', onCanPlay);
        video.removeEventListener('error', onError);
      };

      video.addEventListener('loadedmetadata', onLoadedMetadata, { once: true });
      video.addEventListener('canplay', onCanPlay, { once: true });
      video.addEventListener('error', onError, { once: true });
    });
  };

  const recoverFromHlsFatalError = async (
    video: HTMLVideoElement,
    failedSourceUrl: string,
    proxiedSourceUrl: string
  ): Promise<boolean> => {
    const recoveryKey = `${failedSourceUrl}::${proxiedSourceUrl}`;
    const previousAttempts = hlsRecoveryAttemptedRef.current.get(recoveryKey) ?? 0;
    if (previousAttempts >= 3) {
      return false;
    }
    hlsRecoveryAttemptedRef.current.set(recoveryKey, previousAttempts + 1);

    // For known default studies, always prefer the pinned MP4 fallback first.
    const defaultFallbackUrl = getDefaultStudyFallbackUrl(studyId);
    if (
      defaultFallbackUrl &&
      !looksLikeHlsUrl(defaultFallbackUrl) &&
      defaultFallbackUrl !== config.videoUrl
    ) {
      setConfig((prev) => ({ ...prev, videoUrl: defaultFallbackUrl }));
      const fallbackReady = await ensurePlayableSource(video, defaultFallbackUrl);
      if (fallbackReady) {
        await video.play().catch(() => undefined);
        setVideoError(null);
        reportDiagnostic({
          eventType: 'study_video_playback_recovered',
          severity: 'info',
          errorCode: 'hls_fatal_default_study_fallback',
          message: 'Playback recovered after HLS fatal error via default study fallback source.',
          context: {
            failed_source_url: failedSourceUrl,
            fallback_url: defaultFallbackUrl,
            study_id: studyId
          },
          dedupeKey: `study_video_playback_recovered:hls_fatal_default_study_fallback:${studyId}`
        });
        return true;
      }
    }

    const candidatePool = [
      config.originalVideoUrl?.trim() ?? '',
      unwrapHlsProxySourceUrl(failedSourceUrl) ?? '',
      unwrapHlsProxySourceUrl(proxiedSourceUrl) ?? '',
      failedSourceUrl.trim(),
      proxiedSourceUrl.trim(),
      (video.currentSrc || video.src || '').trim()
    ]
      .map((value) => value.trim())
      .filter((value, index, array) => value.length > 0 && array.indexOf(value) === index)
      .filter((value) => isHttpUrl(value));

    for (const candidate of candidatePool) {
      const hostedUrl = await hostVideoInCloud(candidate);
      if (hostedUrl) {
        const hostedReady = await ensurePlayableSource(video, hostedUrl);
        if (hostedReady) {
          await video.play().catch(() => undefined);
          setVideoError(null);
          reportDiagnostic({
            eventType: 'study_video_playback_recovered',
            severity: 'info',
            errorCode: 'hls_fatal_cloud_host_recovery',
            message: 'Playback recovered after HLS fatal error by hosting the source in cloud.',
            context: {
              failed_source_url: failedSourceUrl,
              recovery_candidate: candidate,
              hosted_url: hostedUrl
            },
            dedupeKey: `study_video_playback_recovered:hls_fatal_cloud_host_recovery:${hostedUrl}`
          });
          return true;
        }
      }

      try {
        const response = await fetch('/api/video/resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: candidate })
        });
        const body = (await response.json().catch(() => null)) as { videoUrl?: string } | null;
        const freshUrl = body?.videoUrl?.trim() ?? '';
        if (!freshUrl || looksLikeHlsUrl(freshUrl)) {
          continue;
        }
        setConfig((prev) => ({
          ...prev,
          videoUrl: freshUrl,
          originalVideoUrl: prev.originalVideoUrl ?? candidate
        }));
        const refreshedReady = await ensurePlayableSource(video, freshUrl);
        if (refreshedReady) {
          await video.play().catch(() => undefined);
          setVideoError(null);
          reportDiagnostic({
            eventType: 'study_video_playback_recovered',
            severity: 'info',
            errorCode: 'hls_fatal_resolver_recovery',
            message: 'Playback recovered after HLS fatal error by refreshing resolver URL.',
            context: {
              failed_source_url: failedSourceUrl,
              recovery_candidate: candidate,
              refreshed_url: freshUrl
            },
            dedupeKey: `study_video_playback_recovered:hls_fatal_resolver_recovery:${freshUrl}`
          });
          return true;
        }
      } catch {
        // Continue trying other recovery candidates.
      }
    }

    if (defaultFallbackUrl && defaultFallbackUrl !== config.videoUrl) {
      setConfig((prev) => ({ ...prev, videoUrl: defaultFallbackUrl }));
      const fallbackReady = await ensurePlayableSource(video, defaultFallbackUrl);
      if (fallbackReady) {
        await video.play().catch(() => undefined);
        setVideoError(null);
        reportDiagnostic({
          eventType: 'study_video_playback_recovered',
          severity: 'info',
          errorCode: 'hls_fatal_default_study_fallback',
          message: 'Playback recovered after HLS fatal error via default study fallback source.',
          context: {
            failed_source_url: failedSourceUrl,
            fallback_url: defaultFallbackUrl,
            study_id: studyId
          },
          dedupeKey: `study_video_playback_recovered:hls_fatal_default_study_fallback:${studyId}`
        });
        return true;
      }
    }

    return false;
  };

  const ensurePlayableSource = async (
    video: HTMLVideoElement,
    sourceUrlRaw: string
  ): Promise<boolean> => {
    const sourceUrl = sourceUrlRaw.trim();
    if (!sourceUrl) {
      reportDiagnostic({
        eventType: 'study_playback_source_empty',
        severity: 'error',
        errorCode: 'empty_source_url',
        message: 'No video source URL was available for playback initialization.',
        dedupeKey: 'study_playback_source_empty'
      });
      return false;
    }

    const originalSourceUrl = (config.originalVideoUrl ?? '').trim();
    const hostingCandidates = [
      originalSourceUrl,
      unwrapHlsProxySourceUrl(sourceUrl) ?? '',
      sourceUrl
    ]
      .map((value) => value.trim())
      .filter((value, index, list) => value.length > 0 && list.indexOf(value) === index)
      .filter((value) => isHttpUrl(value) && !isGithubHostedVideoUrl(value));

    if (!isDefaultStudyWithPinnedFallback) {
      for (const candidate of hostingCandidates) {
        const hostedUrl = await hostVideoInCloud(candidate, { silent: true });
        if (hostedUrl && hostedUrl !== sourceUrl) {
          return ensurePlayableSource(video, hostedUrl);
        }
      }
    }

    if (looksLikeHlsUrl(sourceUrl)) {
      const hlsPlaybackSource = toHlsProxyUrl(sourceUrl);
      try {
        const hlsModule = await import('hls.js');
        const Hls = hlsModule.default;
        if (Hls.isSupported()) {
          if (hlsPlayerRef.current && hlsSourceBoundRef.current === hlsPlaybackSource) {
            return true;
          }
          destroyHlsPlayer();
          const hls = new Hls();
          hlsPlayerRef.current = hls;
          hlsSourceBoundRef.current = hlsPlaybackSource;
          hls.on(Hls.Events.ERROR, (_event, data) => {
            if (data?.fatal) {
              void (async () => {
                const recovered = await recoverFromHlsFatalError(
                  video,
                  sourceUrl,
                  hlsPlaybackSource
                );
                if (recovered) {
                  return;
                }
                const message =
                  'Video playback failed: HLS stream could not be loaded. Use a direct .mp4 URL if available.';
                setVideoError(message);
                reportDiagnostic({
                  eventType: 'study_hls_playback_failed',
                  severity: 'error',
                  errorCode: 'hls_fatal_error',
                  message,
                  context: {
                    source_url: sourceUrl,
                    proxied_source_url: hlsPlaybackSource,
                    hls_error_type:
                      typeof data?.type === 'string' ? data.type : undefined,
                    hls_error_details:
                      typeof data?.details === 'string' ? data.details : undefined
                  },
                  dedupeKey: `study_hls_playback_failed:${sourceUrl}`
                });
              })();
            }
          });
          hls.loadSource(hlsPlaybackSource);
          hls.attachMedia(video);
          return true;
        }
      } catch {
        // Fall back to native HLS playback checks.
      } finally {
        if (!hlsPlayerRef.current) {
          destroyHlsPlayer();
        }
      }

      if (video.canPlayType('application/vnd.apple.mpegurl')) {
        destroyHlsPlayer();
        if ((video.currentSrc || video.src) !== hlsPlaybackSource) {
          video.src = hlsPlaybackSource;
          video.load();
        }
        return true;
      }
    }

    destroyHlsPlayer();
    const candidates = getSourceCandidates(sourceUrl).filter(
      (candidate) => !looksLikeHlsUrl(candidate)
    );
    for (const candidate of candidates) {
      const loaded = await tryLoadVideoSource(video, candidate);
      if (!loaded) {
        continue;
      }

      if (candidate !== sourceUrl) {
        setConfig((prev) => (prev.videoUrl === sourceUrl ? { ...prev, videoUrl: candidate } : prev));
        reportDiagnostic({
          eventType: 'study_video_source_fallback',
          severity: 'warning',
          errorCode: 'fallback_candidate_loaded',
          message: 'Video playback switched to a fallback source candidate.',
          context: {
            requested_source: sourceUrl,
            fallback_source: candidate
          },
          dedupeKey: `study_video_source_fallback:${sourceUrl}:${candidate}`
        });
      }
      return true;
    }
    reportDiagnostic({
      eventType: 'study_playback_source_unavailable',
      severity: 'error',
      errorCode: 'no_playable_source',
      message: 'No playable source candidate succeeded for this study video.',
      context: {
        requested_source: sourceUrl,
        candidates
      },
      dedupeKey: `study_playback_source_unavailable:${sourceUrl}`
    });
    return false;
  };

  useEffect(() => {
    let cancelled = false;

    const loadConfig = async () => {
      setLoadingConfig(true);
      setConfigError(null);
      try {
        let querySuffix = '';
        let resolvedLibraryItem: {
          item: { studyId: string; title: string; videoUrl: string };
        } | null = null;
        if (typeof window !== 'undefined') {
          const currentParams = new URLSearchParams(window.location.search);
          const canonicalParams = new URLSearchParams(currentParams.toString());
          resolvedLibraryItem = applyCanonicalLibraryParams(
            studyId,
            canonicalParams,
            window.localStorage
          );

          const canonicalQuery = canonicalParams.toString();
          if (canonicalQuery !== currentParams.toString()) {
            const nextUrl = canonicalQuery
              ? `${window.location.pathname}?${canonicalQuery}`
              : window.location.pathname;
            window.history.replaceState(null, '', nextUrl);
          }
          querySuffix = canonicalQuery ? `?${canonicalQuery}` : '';
        }

        const response = await fetch(`/api/study/${studyId}/config${querySuffix}`);
        if (!response.ok) {
          throw new Error(`Config request failed (${response.status})`);
        }
        const payload = (await response.json()) as Partial<StudyConfig>;
        if (!cancelled) {
          const resolvedInitialVideoUrl =
            resolvedLibraryItem?.item.videoUrl ?? payload.videoUrl ?? '/sample.mp4';
          const defaultStudyVideoUrl = getDefaultStudyFallbackUrl(studyId);
          const shouldForceDefaultFallback =
            Boolean(defaultStudyVideoUrl) && looksLikeHlsUrl(resolvedInitialVideoUrl);
          const nextVideoUrl =
            shouldForceDefaultFallback && defaultStudyVideoUrl
              ? defaultStudyVideoUrl
              : resolvedInitialVideoUrl;
          const nextOriginalVideoUrl = shouldForceDefaultFallback
            ? null
            : payload.originalVideoUrl ?? null;
          setConfig({
            studyId: payload.studyId ?? studyId,
            videoId: resolvedLibraryItem?.item.studyId ?? payload.videoId ?? `video-${studyId}`,
            title: resolvedLibraryItem?.item.title ?? payload.title ?? `Study ${studyId}`,
            videoUrl: nextVideoUrl,
            originalVideoUrl: nextOriginalVideoUrl,
            dialEnabled: payload.dialEnabled ?? false,
            requireWebcam: payload.requireWebcam ?? false
          });

        }
      } catch (error) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : 'Unable to load the study configuration.';
          setConfigError(
            message
          );
          reportDiagnostic({
            eventType: 'study_config_load_failed',
            severity: 'error',
            errorCode: 'config_fetch_failed',
            message,
            context: {
              study_id: studyId
            },
            dedupeKey: `study_config_load_failed:${studyId}:${message}`
          });
        }
      } finally {
        if (!cancelled) {
          setLoadingConfig(false);
        }
      }
    };

    loadConfig();

    return () => {
      cancelled = true;
    };
  }, [studyId]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      setNextStudyHref(null);
      setNextStudyTitle(null);
      return;
    }

    const currentParams = new URLSearchParams(window.location.search);
    const canonicalParams = new URLSearchParams(currentParams.toString());
    const resolved = applyCanonicalLibraryParams(studyId, canonicalParams, window.localStorage);

    if (canonicalParams.toString() !== currentParams.toString()) {
      const nextUrl = canonicalParams.toString()
        ? `${window.location.pathname}?${canonicalParams.toString()}`
        : window.location.pathname;
      window.history.replaceState(null, '', nextUrl);
    }

    const libraryId = canonicalParams.get('library');
    if (libraryId !== WATCHLAB_LIBRARY_ID) {
      setNextStudyHref(null);
      setNextStudyTitle(null);
      return;
    }

    const items = readVideoLibrary(window.localStorage);
    if (!resolved) {
      setNextStudyHref(null);
      setNextStudyTitle(null);
      return;
    }

    const nextIndex = resolved.index + 1;
    if (nextIndex >= items.length) {
      setNextStudyHref(null);
      setNextStudyTitle(null);
      return;
    }

    const nextItem = items[nextIndex];
    setNextStudyHref(buildStudyHref(nextItem, nextIndex));
    setNextStudyTitle(nextItem.title);
  }, [studyId]);

  useEffect(() => {
    if (stage !== 'watch' && stage !== 'annotation') {
      destroyHlsPlayer();
      return;
    }
    const video = studyVideoRef.current;
    if (!video) {
      return;
    }
    void ensurePlayableSource(video, config.videoUrl || '/sample.mp4');
  }, [stage, config.videoUrl]);

  const nextMonotonicClientMs = () => {
    const candidate = Math.max(0, Math.round(performance.now()));
    const nextValue =
      candidate > monotonicClientTimeRef.current
        ? candidate
        : monotonicClientTimeRef.current + 1;
    monotonicClientTimeRef.current = nextValue;
    return nextValue;
  };

  const pushRollingSample = <T,>(buffer: T[], value: T, maxSize = 16) => {
    buffer.push(value);
    while (buffer.length > maxSize) {
      buffer.shift();
    }
  };

  const computeMean = (values: number[]) => {
    if (values.length === 0) {
      return 0;
    }
    return values.reduce((total, value) => total + value, 0) / values.length;
  };

  const estimateBlurProxy = (
    pixels: Uint8ClampedArray,
    width: number,
    height: number
  ): number => {
    if (width < 3 || height < 3) {
      return 0;
    }

    const luminance = new Float32Array(width * height);
    for (let i = 0, p = 0; i < luminance.length; i += 1, p += 4) {
      const r = pixels[p];
      const g = pixels[p + 1];
      const b = pixels[p + 2];
      luminance[i] = 0.299 * r + 0.587 * g + 0.114 * b;
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

    if (sampleCount === 0) {
      return 0;
    }
    return Number((laplacianEnergy / sampleCount).toFixed(6));
  };

  const sampleSyncedVideoTimeMs = (allowBackward = false) => {
    const video = studyVideoRef.current;
    const measuredMs = video
      ? Math.round(video.currentTime * 1000)
      : videoTimeTrackerRef.current.getVideoTimeMs();
    const nextMs = videoTimeTrackerRef.current.sample({
      measuredVideoTimeMs: measuredMs,
      clientMonotonicMs: performance.now(),
      allowBackward,
      isPlaying: Boolean(video && !video.paused && !video.ended),
      playbackRate: video?.playbackRate ?? 1,
      isBuffering: Boolean(video && !video.paused && !video.ended && video.readyState < 3)
    });
    setVideoTimeMs(nextMs);
    return nextMs;
  };

  const createTimelineEvent = (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward = false,
    explicitVideoTimeMs?: number
  ): TimelineEvent => {
    const resolvedVideoTimeMs =
      typeof explicitVideoTimeMs === 'number'
        ? explicitVideoTimeMs
        : sampleSyncedVideoTimeMs(allowBackward);

    return {
      type,
      sessionId,
      videoId: config.videoId || `video-${studyId}`,
      wallTimeMs: Date.now(),
      clientMonotonicMs: nextMonotonicClientMs(),
      videoTimeMs: resolvedVideoTimeMs,
      details
    };
  };

  const appendEvent = (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward = false,
    explicitVideoTimeMs?: number
  ) => {
    const event = createTimelineEvent(type, details, allowBackward, explicitVideoTimeMs);
    timelineRef.current = [...timelineRef.current, event];
    setTimeline(timelineRef.current);
    return event;
  };

  const appendAbandonmentEvent = (
    reason: string,
    sourceStage: StudyStage,
    explicitVideoTimeMs?: number
  ) => {
    const measuredVideoTimeMs = sampleSyncedVideoTimeMs(true);
    const lastVideoTimeMs =
      typeof explicitVideoTimeMs === 'number'
        ? explicitVideoTimeMs
        : Math.max(lastObservedVideoTimeRef.current, measuredVideoTimeMs);

    const details = {
      reason,
      sourceStage,
      lastVideoTimeMs
    };

    appendEvent('abandonment', details, true, lastVideoTimeMs);
    // Legacy compatibility for older downstream consumers.
    appendEvent('session_incomplete', details, true, lastVideoTimeMs);
    return lastVideoTimeMs;
  };

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
    if (!webcamVideo) {
      return;
    }

    stopFrameCounter();

    const counter = frameCounterRef.current;
    counter.active = true;
    counter.frames = 0;
    counter.lastSampleMs = performance.now();

    const countFrame = () => {
      if (!counter.active) {
        return;
      }
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

  const stopDialSampling = () => {
    if (dialSampleTimerRef.current !== null) {
      window.clearInterval(dialSampleTimerRef.current);
      dialSampleTimerRef.current = null;
    }
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

  useEffect(() => {
    return () => {
      stopWebcam();
      stopDialSampling();
      destroyHlsPlayer();
    };
  }, []);

  // Re-attach webcam stream whenever the video element is replaced (stage transition
  // from 'camera' to 'watch' swaps out the DOM element while the stream stays in streamRef).
  useEffect(() => {
    const video = webcamVideoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) {
      return;
    }
    if (video.srcObject !== stream) {
      video.srcObject = stream;
      video.play().catch(() => {});
    }
    startFrameCounter();
  }, [stage]);

  useEffect(() => {
    if (!isPlaying || !config.dialEnabled || !dialModeEnabled || stage !== 'annotation') {
      stopDialSampling();
      return;
    }

    stopDialSampling();
    dialSampleTimerRef.current = window.setInterval(() => {
      const sample: DialSample = {
        id: safeUuid(),
        wallTimeMs: Date.now(),
        videoTimeMs: sampleSyncedVideoTimeMs(false),
        value: dialValueRef.current
      };
      dialSamplesRef.current.push(sample);
      setDialSampleCount(dialSamplesRef.current.length);
    }, 200);

    return () => {
      stopDialSampling();
    };
  }, [isPlaying, config.dialEnabled, dialModeEnabled, stage]);

  const runQualityCheck = async () => {
    if (qualityCheckInFlightRef.current) {
      return;
    }

    const webcamVideo = webcamVideoRef.current;
    const canvas = qualityCanvasRef.current;

    if (!webcamVideo || !canvas || webcamVideo.readyState < 2) {
      return;
    }

    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) {
      return;
    }

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
        const r = pixels[i];
        const g = pixels[i + 1];
        const b = pixels[i + 2];
        sum += 0.299 * r + 0.587 * g + 0.114 * b;
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
            detect: (input: HTMLVideoElement) => Promise<
              Array<{
                boundingBox?: {
                  x: number;
                  y: number;
                  width: number;
                  height: number;
                };
              }>
            >;
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
              Math.min((box.width * box.height) / (sampleWidth * sampleHeight), 1)
            );
            const centerX = box.x + box.width / 2;
            const centerY = box.y + box.height / 2;
            const dx = Math.abs(centerX - sampleWidth / 2) / Math.max(sampleWidth / 2, 1);
            const dy = Math.abs(centerY - sampleHeight / 2) / Math.max(sampleHeight / 2, 1);
            centerOffset = Math.max(0, Math.min((dx + dy) / 2, 1));

            let touches = 0;
            const marginX = sampleWidth * 0.04;
            const marginY = sampleHeight * 0.04;
            if (box.x <= marginX) {
              touches += 1;
            }
            if (box.x + box.width >= sampleWidth - marginX) {
              touches += 1;
            }
            if (box.y <= marginY) {
              touches += 1;
            }
            if (box.y + box.height >= sampleHeight - marginY) {
              touches += 1;
            }
            borderTouchRatio = touches / 4;
          }
          headPoseValid =
            faceDetected &&
            centerOffset < 0.35 &&
            faceAreaRatio > 0.06 &&
            borderTouchRatio < 0.5;
          const smallFacePenalty = Math.max(0, Math.min((0.06 - faceAreaRatio) / 0.06, 1));
          occlusionScore = Math.max(
            0,
            Math.min(0.55 * borderTouchRatio + 0.45 * smallFacePenalty, 1)
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
        recentFaceVisibleRef.current.map((value) => (value ? 1 : 0))
      );
      const headPoseValidPct = computeMean(
        recentHeadPoseValidRef.current.map((value) => (value ? 1 : 0))
      );
      const qualityScore = computeQualityScore({
        brightness,
        blur,
        fpsStability,
        faceVisiblePct,
        occlusionScore,
        headPoseValidPct
      });
      const trackingConfidence = computeTrackingConfidence({
        faceVisiblePct,
        headPoseValidPct,
        fpsStability,
        qualityScore,
        occlusionScore
      });
      const qualityFlags = detectQualityFlags({
        brightness,
        brightnessScore: litScore,
        blurScore: sharpnessScore,
        faceVisiblePct,
        headPoseValidPct
      });

      const brightnessOk = litScore >= 0.45;
      const fpsOk = fps >= 8 || fpsStability >= 0.45;
      faceOk = faceDetected && faceVisiblePct >= 0.5;
      const pass =
        brightnessOk &&
        fpsOk &&
        faceOk &&
        qualityScore >= 0.45 &&
        !qualityFlags.includes('face_lost');

      if (qualityFlags.includes('low_light')) {
        notes.push('Increase front lighting.');
      }
      if (qualityFlags.includes('blur')) {
        notes.push('Camera looks blurry. Clean lens or steady the device.');
      }
      if (qualityFlags.includes('face_lost')) {
        notes.push('Keep your face centered and visible in frame.');
      }
      if (qualityFlags.includes('high_yaw_pitch') && faceDetectionAvailable) {
        notes.push('Face angle is too steep. Face the screen more directly.');
      }
      if (!fpsOk) {
        notes.push('Camera FPS is unstable; close CPU-heavy apps.');
      }
      if (!pass && notes.length === 0) {
        notes.push('Adjust camera position and lighting, then retry.');
      }

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
        qualityFlags
      };
      qualitySamplesRef.current.push(qualitySample);
      if (qualitySamplesRef.current.length > 1200) {
        qualitySamplesRef.current.shift();
      }

      const updated: QualityState = {
        brightness,
        brightnessScore: litScore,
        blur,
        blurScore: sharpnessScore,
        brightnessOk,
        faceDetected,
        faceVisiblePct: qualitySample.faceVisiblePct,
        headPoseValidPct: qualitySample.headPoseValidPct,
        occlusionScore: qualitySample.occlusionScore,
        faceOk,
        fps,
        fpsStability,
        fpsOk,
        trackingConfidence,
        qualityScore,
        pass,
        qualityFlags,
        notes
      };

      setQuality(updated);

      appendEvent('quality_check', {
        brightness,
        brightnessScore: litScore,
        blur,
        blurScore: sharpnessScore,
        brightnessOk,
        faceDetected,
        faceVisiblePct: qualitySample.faceVisiblePct,
        headPoseValidPct: qualitySample.headPoseValidPct,
        occlusionScore: qualitySample.occlusionScore,
        faceOk,
        fps,
        fpsStability,
        fpsOk,
        pass,
        qualityScore,
        trackingConfidence,
        qualityFlags
      }, false, qualitySample.videoTimeMs);
    } finally {
      qualityCheckInFlightRef.current = false;
    }
  };

  const startFrameCapture = () => {
    const canvas = captureCanvasRef.current;
    if (!canvas) {
      return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return;
    }

    canvas.width = 224;
    canvas.height = 224;

    if (frameCaptureTimerRef.current !== null) {
      window.clearInterval(frameCaptureTimerRef.current);
    }

    frameCaptureTimerRef.current = window.setInterval(() => {
      if (!streamRef.current) {
        return;
      }
      const webcamVideo = webcamVideoRef.current;
      if (!webcamVideo || webcamVideo.readyState < 2) {
        return;
      }

      ctx.drawImage(webcamVideo, 0, 0, 224, 224);
      const jpegData = canvas.toDataURL('image/jpeg', 0.7).split(',')[1] ?? '';
      const timestampMs = Date.now();
      const syncedVideoTimeMs = sampleSyncedVideoTimeMs(false);

      if (framesRef.current.length < MAX_STORED_FRAMES) {
        framesRef.current.push({
          id: safeUuid(),
          timestampMs,
          videoTimeMs: syncedVideoTimeMs,
          jpegBase64: jpegData
        });
      } else {
        framePointersRef.current.push({
          id: safeUuid(),
          timestampMs,
          videoTimeMs: syncedVideoTimeMs,
          pointer: `memory-frame-${framesRef.current.length + framePointersRef.current.length}`
        });
      }
      setCapturedFrameCount(framesRef.current.length + framePointersRef.current.length);
    }, 200);
  };

  const startWebcamChecks = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setWebcamStatus('denied');
      setQuality({
        ...DEFAULT_QUALITY,
        notes: ['This browser does not support webcam capture.']
      });
      appendEvent('webcam_denied', { reason: 'unsupported' });
      return;
    }

    setWebcamStatus('requesting');

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          width: { ideal: 640 },
          height: { ideal: 480 },
          frameRate: { ideal: 30, min: 10 }
        }
      });

      streamRef.current = stream;

      // Watchdog: detect unexpected stream loss mid-session and recover.
      stream.getTracks().forEach((track) => {
        track.addEventListener('ended', () => {
          if (stageRef.current === 'watch' || stageRef.current === 'camera') {
            appendEvent('webcam_device_lost', { trackKind: track.kind });
            setWebcamStatus('denied');
            setQuality({ ...DEFAULT_QUALITY, notes: ['Camera disconnected. Please reconnect and retry.'] });
            stopWebcamCaptureLoops();
            // Auto-retry once after brief delay to handle temporary device interrupts.
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
        runQualityCheck().catch(() => {
          // Keep sampling even if one iteration fails.
        });
      }, QUALITY_SAMPLE_INTERVAL_MS);

      startFrameCapture();
    } catch (error) {
      setWebcamStatus('denied');
      setQuality({
        ...DEFAULT_QUALITY,
        notes: [
          error instanceof Error ? error.message : 'Webcam permission was denied or unavailable.'
        ]
      });
      appendEvent('webcam_denied', {
        reason: error instanceof Error ? error.message : 'unknown'
      });
    }
  };

  const onAgree = async () => {
    setConsented(true);
    setStage('camera');
    setWebcamBypassed(false);
    setVideoCompleted(false);
    setFirstPassEnded(false);
    setAudioCheckPlayed(false);
    setAudioConfirmed(false);
    setAnnotationMarkers([]);
    setAnnotationSkipped(false);
    annotationSkippedRef.current = false;
    setAnnotationNoteDraft('');
    setAnnotationCursorMs(0);
    setAnnotationDurationMs(0);
    setDialModeEnabled(false);
    setDialValue(50);
    dialSamplesRef.current = [];
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
    setDialSampleCount(0);
    if (typeof window !== 'undefined') {
      saveParticipantInfo(window.localStorage, participantName.trim(), participantEmail.trim());
    }
    appendEvent('consent_accepted');
    await startWebcamChecks();
  };

  // Called when arriving at a subsequent video in a sequence (returning=1 URL param).
  // Skips onboarding and camera setup — restores saved participant info, silently starts
  // webcam, and goes straight to the watch stage.
  const startReturningSession = async () => {
    if (typeof window !== 'undefined') {
      const saved = readParticipantInfo(window.localStorage);
      if (saved) {
        setParticipantName(saved.name);
        setParticipantEmail(saved.email);
      }
    }
    setConsented(true);
    setStage('watch');
    setWebcamBypassed(false);
    setVideoCompleted(false);
    setFirstPassEnded(false);
    setAudioCheckPlayed(false);
    setAudioConfirmed(false);
    setAnnotationMarkers([]);
    setAnnotationSkipped(false);
    annotationSkippedRef.current = false;
    setAnnotationNoteDraft('');
    setAnnotationCursorMs(0);
    setAnnotationDurationMs(0);
    setDialModeEnabled(false);
    setDialValue(50);
    dialSamplesRef.current = [];
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
    setDialSampleCount(0);
    appendEvent('consent_accepted');
    // Start webcam silently — don't wait for quality pass before showing video
    startWebcamChecks().catch(() => undefined);
  };

  // Trigger returning-participant fast-path once config has loaded
  useEffect(() => {
    if (!isReturningParticipant || loadingConfig || configError) return;
    void startReturningSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReturningParticipant, loadingConfig, configError]);

  const onRetryWebcam = async () => {
    stopWebcam();
    setWebcamBypassed(false);
    setQuality(DEFAULT_QUALITY);
    setCapturedFrameCount(0);
    framesRef.current = [];
    framePointersRef.current = [];
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
    await startWebcamChecks();
  };

  const onContinueWithoutWebcam = () => {
    if (config.requireWebcam) {
      return;
    }
    stopWebcam();
    setWebcamBypassed(true);
    setWebcamStatus('denied');
    setQuality({
      ...DEFAULT_QUALITY,
      notes: ['Proceeding without webcam capture for this session.']
    });
    setCapturedFrameCount(0);
    framesRef.current = [];
    framePointersRef.current = [];
    qualitySamplesRef.current = [];
    recentFpsRef.current = [];
    recentFaceVisibleRef.current = [];
    recentHeadPoseValidRef.current = [];
    appendEvent('webcam_denied', {
      reason: 'participant_opted_out',
      optionalPath: true
    });
  };

  const playAudioCheckTone = async () => {
    const AudioContextCtor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof window.AudioContext }).webkitAudioContext;

    if (!AudioContextCtor) {
      return;
    }

    const audioContext = new AudioContextCtor();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = 'sine';
    oscillator.frequency.value = 660;
    gainNode.gain.value = 0.08;

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.start();
    window.setTimeout(() => {
      oscillator.stop();
      audioContext.close().catch(() => undefined);
    }, 500);

    setAudioCheckPlayed(true);
  };

  const onStartStudyVideo = () => {
    setStage('watch');
    setVideoError(null);
    setAnnotationSkipped(false);
    annotationSkippedRef.current = false;
    setFirstPassEnded(false);
    videoTimeTrackerRef.current.seek(0, performance.now());
    setVideoTimeMs(0);
    lastObservedVideoTimeRef.current = 0;
    seekStartVideoTimeRef.current = null;
    isMutedRef.current = false;
    lastVolumeRef.current = 1;
    appendEvent(
      'playback_started',
      {
        mode: 'passive_first_viewing',
        webcamEnabled: !webcamBypassed
      },
      true,
      0
    );

    window.setTimeout(() => {
      const video = studyVideoRef.current;
      if (!video) {
        return;
      }
      video.currentTime = 0;
      video
        .play()
        .then(() => {
          setVideoError(null);
        })
        .catch((error) => {
          setVideoError(
            `Video playback failed: ${error instanceof Error ? error.message : 'unknown error'}`
          );
        });
    }, 0);
  };

  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    let rafId = 0;
    const tick = () => {
      const video = studyVideoRef.current;
      if (video) {
        const measuredMs = sampleSyncedVideoTimeMs(false);
        lastObservedVideoTimeRef.current = measuredMs;

        const debugStore = (window as Window & {
          __watchlabDebug?: { videoTimeSamples: number[] };
        }).__watchlabDebug;

        if (debugStore) {
          debugStore.videoTimeSamples.push(measuredMs);
          if (debugStore.videoTimeSamples.length > 60) {
            debugStore.videoTimeSamples.shift();
          }
        }
      }
      rafId = window.requestAnimationFrame(tick);
    };

    rafId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafId);
  }, [isPlaying]);

  const syncClockFromVideo = (allowBackward = false) => {
    const current = sampleSyncedVideoTimeMs(allowBackward);
    lastObservedVideoTimeRef.current = current;
    if (stageRef.current === 'annotation') {
      setAnnotationCursorMs(current);
    }
  };

  const onVideoSeeked = (mode: 'first_pass' | 'annotation') => {
    const seekStartVideoTimeMs =
      seekStartVideoTimeRef.current ?? lastObservedVideoTimeRef.current;
    const measuredMs = studyVideoRef.current ? Math.round(studyVideoRef.current.currentTime * 1000) : 0;
    const currentVideoTimeMs = videoTimeTrackerRef.current.seek(measuredMs, performance.now());
    setVideoTimeMs(currentVideoTimeMs);

    appendEvent(
      'seek_end',
      {
        mode,
        fromVideoTimeMs: seekStartVideoTimeMs,
        toVideoTimeMs: currentVideoTimeMs
      },
      true,
      currentVideoTimeMs
    );

    appendEvent(
      'seek',
      {
        mode,
        fromVideoTimeMs: seekStartVideoTimeMs,
        toVideoTimeMs: currentVideoTimeMs
      },
      true,
      currentVideoTimeMs
    );

    if (currentVideoTimeMs + 250 < seekStartVideoTimeMs) {
      appendEvent(
        'rewind',
        {
          mode,
          fromVideoTimeMs: seekStartVideoTimeMs,
          toVideoTimeMs: currentVideoTimeMs
        },
        true,
        currentVideoTimeMs
      );
    }

    lastObservedVideoTimeRef.current = currentVideoTimeMs;
    if (mode === 'annotation') {
      setAnnotationCursorMs(currentVideoTimeMs);
    }
    seekStartVideoTimeRef.current = null;
  };

  const onVideoSeeking = (mode: 'first_pass' | 'annotation') => {
    const previousVideoTimeMs = lastObservedVideoTimeRef.current;
    seekStartVideoTimeRef.current = previousVideoTimeMs;
    const tentativeToVideoTimeMs = studyVideoRef.current
      ? Math.round(studyVideoRef.current.currentTime * 1000)
      : previousVideoTimeMs;
    appendEvent(
      'seek_start',
      {
        mode,
        fromVideoTimeMs: previousVideoTimeMs,
        toVideoTimeMs: tentativeToVideoTimeMs
      },
      true,
      previousVideoTimeMs
    );
  };

  const onVideoVolumeChange = (mode: 'first_pass' | 'annotation') => {
    const video = studyVideoRef.current;
    if (!video) {
      return;
    }

    const previousMuted = isMutedRef.current;
    const previousVolume = lastVolumeRef.current;
    const muted = video.muted || video.volume === 0;

    appendEvent('volume_change', {
      mode,
      fromMuted: previousMuted,
      toMuted: muted,
      fromVolume: previousVolume,
      toVolume: video.volume
    });

    if (muted !== previousMuted) {
      appendEvent(muted ? 'mute' : 'unmute', {
        mode,
        muted,
        volume: video.volume
      });
    }

    isMutedRef.current = muted;
    lastVolumeRef.current = video.volume;
  };

  const toSurveyStage = () => {
    setIsPlaying(false);
    // Ensure videoCompleted is set — the user has progressed past the video
    // stage (either via onEnded or annotation skip/continue) so the survey
    // submit button must be enabled once scores are entered.
    setVideoCompleted(true);
    setStage('survey');
  };

  const getCurrentAnnotationTimeMs = () => {
    const video = studyVideoRef.current;
    if (video) {
      return Math.max(0, Math.round(video.currentTime * 1000));
    }
    return Math.max(0, annotationCursorMs);
  };

  const addMarker = (markerType: MarkerType) => {
    const videoTimeForMarker = getCurrentAnnotationTimeMs();
    const note = annotationNoteDraft.trim();
    const marker: AnnotationMarker = {
      id: safeUuid(),
      sessionId,
      videoId: config.videoId || `video-${studyId}`,
      markerType,
      videoTimeMs: videoTimeForMarker,
      note: note.length > 0 ? note : null,
      createdAt: new Date().toISOString()
    };

    setAnnotationMarkers((prev) => [...prev, marker]);
    setAnnotationSkipped(false);
    setAnnotationNoteDraft('');

    appendEvent(
      'annotation_tag_set',
      {
        markerType,
        markerLabel: markerLabels[markerType],
        videoTimeMs: videoTimeForMarker,
        hasNote: Boolean(marker.note)
      },
      true,
      videoTimeForMarker
    );
  };

  const removeMarker = (markerId: string) => {
    const marker = annotationMarkersRef.current.find((entry) => entry.id === markerId);
    setAnnotationMarkers((prev) => prev.filter((entry) => entry.id !== markerId));
    if (marker) {
      appendEvent(
        'annotation_tag_set',
        {
          action: 'removed',
          markerType: marker.markerType,
          videoTimeMs: marker.videoTimeMs
        },
        true,
        marker.videoTimeMs
      );
    }
  };

  const seekAnnotationTimeline = (nextVideoTimeMs: number) => {
    const clampedMs = Math.max(0, Math.min(nextVideoTimeMs, annotationDurationMs || nextVideoTimeMs));
    const video = studyVideoRef.current;
    if (video) {
      video.currentTime = clampedMs / 1000;
    }
    const syncedMs = videoTimeTrackerRef.current.seek(clampedMs, performance.now());
    setVideoTimeMs(syncedMs);
    lastObservedVideoTimeRef.current = clampedMs;
    setAnnotationCursorMs(clampedMs);
  };

  const markerCounts = useMemo(() => {
    const counts: Record<MarkerType, number> = {
      engaging_moment: 0,
      confusing_moment: 0,
      stop_watching_moment: 0,
      cta_landed_moment: 0
    };

    for (const marker of annotationMarkers) {
      counts[marker.markerType] += 1;
    }

    return counts;
  }, [annotationMarkers]);

  const surveyAnalyticsHighlights = useMemo(
    () =>
      buildSurveyAnalyticsHighlights(
        timeline,
        annotationMarkers,
        qualitySamplesRef.current
      ),
    [timeline, annotationMarkers, stage]
  );


  const hasQualitySample = quality.brightness > 0 || quality.fps > 0 || quality.faceDetected;
  const qualityGatePassed = !hasQualitySample || quality.pass;
  const webcamReady = webcamStatus === 'granted' && qualityGatePassed;
  const bypassReady = !config.requireWebcam && webcamBypassed;
  const canStartPlayback = !loadingConfig && !configError && (webcamReady || bypassReady);
  const canAdvanceFromCamera = canStartPlayback && audioConfirmed;
  const overallEngagementScore = parseSurveyScore(surveyOverallEngagement);
  const contentClarityScore = parseSurveyScore(surveyContentClarity);
  const canFinishSession =
    stage === 'survey' &&
    videoCompleted &&
    overallEngagementScore !== null &&
    contentClarityScore !== null;

  const qualityClass = useMemo(() => {
    if (webcamStatus !== 'granted') {
      return 'status-warn';
    }
    return quality.pass ? 'status-good' : 'status-bad';
  }, [quality.pass, webcamStatus]);
  const cameraQualityNotes = useMemo(
    () =>
      quality.notes.filter(
        (note) => !/face\s*detection\s*api\s*is\s*unavailable/i.test(note)
      ),
    [quality.notes]
  );

  const buildSessionQualitySummary = (): SessionQualitySummary => {
    const samples = qualitySamplesRef.current;
    if (samples.length === 0) {
      return {
        sampleCount: 0,
        meanTrackingConfidence: 0,
        meanQualityScore: 0,
        lowConfidenceWindowCount: 0,
        usableSeconds: 0
      };
    }

    const meanTrackingConfidence =
      samples.reduce((total, sample) => total + sample.trackingConfidence, 0) / samples.length;
    const meanQualityScore =
      samples.reduce((total, sample) => total + sample.qualityScore, 0) / samples.length;
    const lowWindows = detectLowConfidenceWindows(samples);
    const durationMs = Math.max(
      ...samples.map((sample) => sample.videoTimeMs + sample.sampleWindowMs),
      0
    );
    const lowDurationMs = lowWindows.reduce(
      (total, window) => total + Math.max(window.endVideoTimeMs - window.startVideoTimeMs, 0),
      0
    );
    const usableSeconds = Math.max(durationMs - lowDurationMs, 0) / 1000;

    return {
      sampleCount: samples.length,
      meanTrackingConfidence: Number(meanTrackingConfidence.toFixed(6)),
      meanQualityScore: Number(meanQualityScore.toFixed(6)),
      lowConfidenceWindowCount: lowWindows.length,
      usableSeconds: Number(usableSeconds.toFixed(3))
    };
  };

  const getCanonicalTraceRows = (): TraceRow[] =>
    buildCanonicalTraceRows({
      dialSamples: dialSamplesRef.current,
      qualitySamples: qualitySamplesRef.current,
      timeline: timelineRef.current,
      annotationDurationMs
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
        pointer: 'no-webcam-data'
      });
    }

    return {
      studyId,
      videoId: config.videoId,
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
      framePointers: framePointersRef.current
    };
  };

  const uploadSession = async (surveyResponses: SurveyResponse[]) => {
    const payload = buildPayload(surveyResponses);

    const validation = uploadPayloadSchema.safeParse(payload);
    if (!validation.success) {
      setUploadStatus('Upload blocked: payload failed local schema validation.');
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
        body: serialized
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
          if (attempt < MAX_ATTEMPTS) {
            continue;
          }
        }
      }

      if (!response) {
        throw lastError;
      }

      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { error?: string };
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
        (warning): warning is string => typeof warning === 'string' && warning.length > 0
      );
      const warningSuffix = uploadWarnings.length > 0 ? ` — ${uploadWarnings.join(' — ')}` : '';

      setUploadStatus(
        biographVideoId
          ? `Upload complete: session ${body.sessionId} (video ${biographVideoId})${warningSuffix}`
          : `Upload complete: session ${body.sessionId}${warningSuffix}`
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
        `Upload failed: ${error instanceof Error ? error.message : 'Unknown server error'}`
      );
      appendEvent('upload_failed', {
        reason: error instanceof Error ? error.message : 'unknown'
      });
    }
  };

  const finishAndUpload = async () => {
    if (overallEngagementScore === null || contentClarityScore === null) {
      setUploadStatus('Enter both scores as whole numbers between 1 and 5 before finishing.');
      return;
    }

    appendEvent('survey_answered', {
      markerCount: annotationMarkersRef.current.length,
      annotationSkipped: annotationSkippedRef.current,
      overallEngagement: overallEngagementScore,
      contentClarity: contentClarityScore,
      hasComment: surveyAdditionalComments.trim().length > 0
    });
    appendEvent('finish_clicked');

    const surveyResponses: SurveyResponse[] = [
      {
        questionKey: 'annotation_status',
        responseJson: {
          annotation_skipped: annotationSkippedRef.current,
          marker_count: annotationMarkersRef.current.length
        }
      },
      {
        questionKey: 'session_completion_status',
        responseJson: {
          status: 'completed',
          session_id: sessionId
        }
      },
      {
        questionKey: 'overall_interest_likert',
        responseNumber: overallEngagementScore
      },
      {
        questionKey: 'recall_comprehension_likert',
        responseNumber: contentClarityScore
      },
      {
        questionKey: 'survey_score_inputs',
        responseJson: {
          overall_engagement: overallEngagementScore,
          content_clarity: contentClarityScore
        }
      }
    ];

    if (surveyAdditionalComments.trim()) {
      surveyResponses.push({
        questionKey: 'post_annotation_comment',
        responseText: surveyAdditionalComments.trim()
      });
    }

    await uploadSession(surveyResponses);
  };

  const finishEarlyAndUpload = async () => {
    const abandonmentVideoTimeMs = appendAbandonmentEvent(
      'user_ended_early',
      stageRef.current
    );
    if (streamRef.current) {
      appendEvent(
        'webcam_capture_stopped',
        { reason: 'user_ended_early' },
        true,
        abandonmentVideoTimeMs
      );
      stopWebcam();
    }

    const surveyResponses: SurveyResponse[] = [
      {
        questionKey: 'session_completion_status',
        responseJson: {
          status: 'incomplete',
          reason: 'user_ended_early',
          session_id: sessionId,
          last_video_time_ms: abandonmentVideoTimeMs
        }
      }
    ];

    await uploadSession(surveyResponses);
  };

  useEffect(() => {
    const onVisibilityChange = () => {
      if (!isPlaybackTelemetryStage(stageRef.current)) {
        return;
      }

      appendEvent(
        document.visibilityState === 'hidden' ? 'visibility_hidden' : 'visibility_visible',
        {
          visibilityState: document.visibilityState
        }
      );
    };

    const onWindowBlur = () => {
      if (!isPlaybackTelemetryStage(stageRef.current)) {
        return;
      }
      appendEvent('window_blur', { hasFocus: false });
    };

    const onWindowFocus = () => {
      if (!isPlaybackTelemetryStage(stageRef.current)) {
        return;
      }
      appendEvent('window_focus', { hasFocus: true });
    };

    const onFullscreenChange = () => {
      if (!isPlaybackTelemetryStage(stageRef.current)) {
        return;
      }
      appendEvent(document.fullscreenElement ? 'fullscreen_enter' : 'fullscreen_exit', {
        fullscreenEnabled: Boolean(document.fullscreenElement)
      });
    };

    const onPageHide = () => {
      if (uploadTriggeredRef.current) {
        return;
      }

      const currentStage = stageRef.current;
      if (currentStage === 'watch' || currentStage === 'annotation' || currentStage === 'survey') {
        const lastVideoTimeMs = Math.max(
          lastObservedVideoTimeRef.current,
          sampleSyncedVideoTimeMs(true)
        );
        const details = {
          reason: 'pagehide_before_completion',
          sourceStage: currentStage,
          lastVideoTimeMs
        };
        const abandonmentEvent = createTimelineEvent(
          'abandonment',
          details,
          true,
          lastVideoTimeMs
        );
        const legacyIncompleteEvent = createTimelineEvent(
          'session_incomplete',
          details,
          true,
          lastVideoTimeMs
        );
        timelineRef.current = [...timelineRef.current, abandonmentEvent, legacyIncompleteEvent];

        const payload = buildPayload([
          {
            questionKey: 'session_completion_status',
            responseJson: {
              status: 'incomplete',
              reason: 'pagehide_before_completion',
              session_id: sessionId,
              last_video_time_ms: lastVideoTimeMs
            }
          }
        ]);

        const validation = uploadPayloadSchema.safeParse(payload);
        if (!validation.success || typeof navigator.sendBeacon !== 'function') {
          return;
        }

        const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        uploadTriggeredRef.current = true;
        navigator.sendBeacon('/api/upload', blob);
      }
    };

    document.addEventListener('visibilitychange', onVisibilityChange);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    window.addEventListener('blur', onWindowBlur);
    window.addEventListener('focus', onWindowFocus);
    window.addEventListener('pagehide', onPageHide);

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      window.removeEventListener('blur', onWindowBlur);
      window.removeEventListener('focus', onWindowFocus);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, [annotationSkipped, config.videoId, stage, studyId]);

  const resolveVideoErrorMessage = (video: HTMLVideoElement, thrown?: unknown): string => {
    const thrownMessage =
      thrown instanceof Error && typeof thrown.message === 'string'
        ? thrown.message.toLowerCase()
        : '';
    const candidateUrl = video.currentSrc || video.src || '';

    if (
      thrownMessage.includes('no supported source was found') ||
      thrownMessage.includes('media resource indicated by the src attribute')
    ) {
      if (looksLikeWebPageUrl(candidateUrl)) {
        return 'Video playback failed: this URL appears to be a webpage, not a direct video file.';
      }
      if (looksLikeHlsUrl(candidateUrl)) {
        return 'Video playback failed: HLS stream format needs a compatible stream source. Try a direct .mp4 URL if available.';
      }
      return 'Video playback failed: no supported source was found.';
    }

    const mediaError = video.error;
    if (!mediaError) {
      return thrown instanceof Error && thrown.message
        ? `Video playback failed: ${thrown.message}`
        : 'Unknown video playback error.';
    }

    switch (mediaError.code) {
      case mediaError.MEDIA_ERR_ABORTED:
        return 'Video playback was aborted.';
      case mediaError.MEDIA_ERR_NETWORK:
        return 'Network error while loading video.';
      case mediaError.MEDIA_ERR_DECODE:
        return 'Video decode error. Try reloading the page.';
      case mediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
        return looksLikeWebPageUrl(candidateUrl)
          ? 'Video playback failed: this URL appears to be a webpage, not a direct video file. Re-open from Upload so WatchLab can resolve the embedded video source.'
          : looksLikeHlsUrl(candidateUrl)
            ? 'Video playback failed: HLS stream format is not supported with this source in the current browser.'
          : 'Video source is not supported in this browser.';
      default:
        return 'Unknown video playback error.';
    }
  };

  useEffect(() => {
    (window as Window & { __watchlabDebug?: { videoTimeSamples: number[] } }).__watchlabDebug = {
      videoTimeSamples: []
    };
  }, []);

  const webcamPreviewClassName =
    stage === 'camera'
      ? 'webcam-preview webcam-preview-camera'
      : stage === 'watch'
        ? 'webcam-preview webcam-preview-watch'
        : 'webcam-preview webcam-preview-hidden';

  if (!consented || stage === 'onboarding') {
    return (
      <StudyOnboarding
        title={config.title}
        studyId={studyId}
        loadingConfig={loadingConfig}
        participantName={participantName}
        participantEmail={participantEmail}
        setParticipantName={setParticipantName}
        setParticipantEmail={setParticipantEmail}
        onAgree={onAgree}
      />
    );
  }

  if (stage === 'camera') {
    return (
      <StudyCameraCheck
        webcamVideoRef={webcamVideoRef}
        qualityCanvasRef={qualityCanvasRef}
        captureCanvasRef={captureCanvasRef}
        quality={quality}
        webcamStatus={webcamStatus}
        webcamBypassed={webcamBypassed}
        audioCheckPlayed={audioCheckPlayed}
        audioConfirmed={audioConfirmed}
        canAdvanceFromCamera={canAdvanceFromCamera}
        requireWebcam={config.requireWebcam}
        onRetryWebcam={onRetryWebcam}
        onContinueWithoutWebcam={onContinueWithoutWebcam}
        playAudioCheckTone={playAudioCheckTone}
        setAudioConfirmed={setAudioConfirmed}
        onStartStudyVideo={onStartStudyVideo}
      />
    );
  }

  return (
    <main>
      <div className="stack study-shell" data-testid="study-shell">
        <video
          ref={webcamVideoRef}
          width={224}
          height={168}
          muted
          autoPlay
          playsInline
          className={webcamPreviewClassName}
          data-testid="webcam-preview"
        />
        <canvas ref={qualityCanvasRef} style={{ display: 'none' }} />
        <canvas ref={captureCanvasRef} style={{ display: 'none' }} />

        <div className="panel stack">
          <h1>{loadingConfig ? 'Loading study...' : config.title}</h1>
          <p>
            Study ID: <code>{studyId}</code> | Session ID: <code>{sessionId}</code>
          </p>
          <p>
            Participant ID: <code>{participantId}</code>
          </p>
          {configError ? <p className="status-bad">{configError}</p> : null}
          <p>
            Webcam: <strong>{webcamStatus}</strong>{' '}
            <span className={qualityClass}>
              {webcamStatus === 'granted'
                ? quality.pass
                  ? '(quality pass)'
                  : '(quality fail)'
                : ''}
            </span>
          </p>
          <small>
            Brightness: {quality.brightness.toFixed(1)} | Face: {quality.faceDetected ? 'yes' : 'no'} |
            FPS: {quality.fps.toFixed(1)} | FPS stability: {(quality.fpsStability * 100).toFixed(0)}% |
            Tracking confidence: {(quality.trackingConfidence * 100).toFixed(0)}% | Captured frames:{' '}
            {capturedFrameCount}
          </small>
        </div>

        {stage === 'watch' ? (
          <section className="panel stack immersive-stage" data-testid="watch-stage">
            <h2>Passive First Viewing</h2>
            <p className="muted">
              Watch naturally. After playback, you will go straight to the post-video survey.
            </p>
            <video
              ref={studyVideoRef}
              controls
              preload="auto"
              playsInline
              className="immersive-video"
              onPlay={() => {
                setIsPlaying(true);
                videoTimeTrackerRef.current.setPlaybackState({ isPlaying: true, isBuffering: false });
                syncClockFromVideo(false);
                appendEvent('play', { mode: 'first_pass' });
              }}
              onPause={() => {
                setIsPlaying(false);
                videoTimeTrackerRef.current.setPlaybackState({ isPlaying: false, isBuffering: false });
                syncClockFromVideo(false);
                appendEvent('pause', { mode: 'first_pass' });
              }}
              onSeeking={() => {
                onVideoSeeking('first_pass');
              }}
              onSeeked={() => {
                onVideoSeeked('first_pass');
              }}
              onVolumeChange={() => {
                onVideoVolumeChange('first_pass');
              }}
              onRateChange={(event) => {
                videoTimeTrackerRef.current.setPlaybackState({
                  playbackRate: event.currentTarget.playbackRate
                });
                syncClockFromVideo(false);
              }}
              onWaiting={() => {
                videoTimeTrackerRef.current.setPlaybackState({ isBuffering: true });
                syncClockFromVideo(false);
              }}
              onStalled={() => {
                videoTimeTrackerRef.current.setPlaybackState({ isBuffering: true });
                syncClockFromVideo(false);
              }}
              onPlaying={() => {
                videoTimeTrackerRef.current.setPlaybackState({ isBuffering: false, isPlaying: true });
                syncClockFromVideo(false);
              }}
              onEnded={() => {
                setIsPlaying(false);
                videoTimeTrackerRef.current.setPlaybackState({ isPlaying: false, isBuffering: false });
                setVideoCompleted(true);
                setFirstPassEnded(true);
                const endedVideoTimeMs = sampleSyncedVideoTimeMs(false);
                lastObservedVideoTimeRef.current = endedVideoTimeMs;
                setAnnotationCursorMs(0);
                appendEvent('ended', { mode: 'first_pass' }, true, endedVideoTimeMs);
                if (streamRef.current) {
                  appendEvent(
                    'webcam_capture_stopped',
                    { reason: 'first_pass_completed' },
                    true,
                    endedVideoTimeMs
                  );
                  stopWebcam();
                }
                annotationSkippedRef.current = true;
                setAnnotationSkipped(true);
                appendEvent(
                  'annotation_mode_skipped',
                  { reason: 'auto_survey_after_playback', explicitSkip: false },
                  true,
                  endedVideoTimeMs
                );
                setStage('survey');
              }}
              onTimeUpdate={() => {
                if (!isPlaying) {
                  syncClockFromVideo(false);
                }
              }}
              onLoadedData={() => {
                setVideoError(null);
                const video = studyVideoRef.current;
                isMutedRef.current = video ? video.muted || video.volume === 0 : false;
                lastVolumeRef.current = video?.volume ?? 1;
                videoTimeTrackerRef.current.setPlaybackState({
                  isPlaying: false,
                  isBuffering: false
                });
              }}
              onError={(event) => {
                const target = event.currentTarget;
                const candidateUrl = target.currentSrc || target.src || '';
                void (async () => {
                  const recoverySource = pickRecoverySource(
                    candidateUrl,
                    config.videoUrl,
                    config.originalVideoUrl ?? null
                  );
                  const hostedUrl = await hostVideoInCloud(recoverySource);
                  if (hostedUrl && studyVideoRef.current) {
                    const recovered = await ensurePlayableSource(studyVideoRef.current, hostedUrl);
                    if (recovered) {
                      setVideoError(null);
                      reportDiagnostic({
                        eventType: 'study_video_playback_recovered',
                        severity: 'info',
                        errorCode: 'cloud_host_recovery',
                        message: 'Video playback recovered using hosted fallback source.',
                        context: {
                          candidate_url: candidateUrl,
                          hosted_url: hostedUrl
                        },
                        dedupeKey: `study_video_playback_recovered:${hostedUrl}`
                      });
                      return;
                    }
                  }

                  const resolverSource = pickRecoverySource(
                    candidateUrl,
                    recoverySource,
                    config.videoUrl,
                    config.originalVideoUrl ?? null
                  );
                  if (isHttpUrl(resolverSource)) {
                    try {
                      const response = await fetch('/api/video/resolve', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: resolverSource })
                      });
                      const body = (await response.json().catch(() => null)) as {
                        videoUrl?: string;
                      } | null;
                      const freshUrl = body?.videoUrl?.trim() ?? '';
                      const canUseFreshUrl =
                        freshUrl.length > 0 &&
                        (!isDefaultStudyWithPinnedFallback || !looksLikeHlsUrl(freshUrl));
                      if (canUseFreshUrl && studyVideoRef.current) {
                        setConfig((prev) => ({ ...prev, videoUrl: freshUrl }));
                        const recovered = await ensurePlayableSource(studyVideoRef.current, freshUrl);
                        if (recovered) {
                          setVideoError(null);
                          reportDiagnostic({
                            eventType: 'study_video_playback_recovered',
                            severity: 'info',
                            errorCode: 'resolver_refresh_recovery',
                            message: 'Video playback recovered with a refreshed resolver URL.',
                            context: {
                              candidate_url: candidateUrl,
                              resolver_source: resolverSource,
                              refreshed_url: freshUrl
                            },
                            dedupeKey: `study_video_playback_recovered:resolver:${freshUrl}`
                          });
                          return;
                        }
                      }
                    } catch {
                      // Fall through to show the error message.
                    }
                  }

                  const baseMsg = resolveVideoErrorMessage(target);
                  const finalMessage = !config.originalVideoUrl
                    ? `${baseMsg} This source is not GitHub-hosted yet — open Upload and host it in cloud.`
                    : baseMsg;
                  setVideoError(finalMessage);
                  reportDiagnostic({
                    eventType: 'study_video_playback_failed',
                    severity: 'error',
                    errorCode: looksLikeHlsUrl(candidateUrl)
                      ? 'hls_source_not_supported'
                      : looksLikeWebPageUrl(candidateUrl)
                        ? 'webpage_source_not_video'
                        : 'unsupported_source',
                    message: finalMessage,
                    context: {
                      candidate_url: candidateUrl,
                      has_original_video_url: Boolean(config.originalVideoUrl)
                    },
                    dedupeKey: `study_video_playback_failed:${candidateUrl}:${finalMessage}`
                  });
                })();
              }}
              data-testid="study-video"
            />
            <div className="row immersive-controls">
              <button
                className="primary"
                onClick={async () => {
                  const video = studyVideoRef.current;
                  if (!video) {
                    return;
                  }
                  const sourceReady = await ensurePlayableSource(
                    video,
                    config.videoUrl || '/sample.mp4'
                  );
                  if (!sourceReady) {
                    const message =
                      'Video playback failed: unable to initialize this source in the current browser.';
                    setVideoError(message);
                    reportDiagnostic({
                      eventType: 'study_video_playback_failed',
                      severity: 'error',
                      errorCode: 'source_init_failed',
                      message,
                      context: {
                        configured_video_url: config.videoUrl
                      },
                      dedupeKey: `study_video_playback_failed:source_init_failed:${config.videoUrl}`
                    });
                    return;
                  }

                  video
                    .play()
                    .then(() => {
                      setVideoError(null);
                    })
                    .catch(async (error) => {
                      const msg = error instanceof Error ? error.message.toLowerCase() : '';
                      const isSourceError =
                        msg.includes('no supported source') ||
                        msg.includes('media resource') ||
                        video.error?.code === video.error?.MEDIA_ERR_SRC_NOT_SUPPORTED;
                      if (isSourceError) {
                        const recoverySource = pickRecoverySource(
                          video.currentSrc || video.src || '',
                          config.videoUrl,
                          config.originalVideoUrl ?? null
                        );
                        const hostedUrl = await hostVideoInCloud(recoverySource);
                        if (hostedUrl) {
                          const hostedReady = await ensurePlayableSource(video, hostedUrl);
                          if (hostedReady) {
                            await video.play();
                            setVideoError(null);
                            reportDiagnostic({
                              eventType: 'study_video_playback_recovered',
                              severity: 'info',
                              errorCode: 'play_click_cloud_host_recovery',
                              message: 'Playback recovered after source hosting fallback during play.',
                              context: {
                                hosted_url: hostedUrl
                              },
                              dedupeKey: `study_video_playback_recovered:play_click:${hostedUrl}`
                            });
                            return;
                          }
                        }
                      }
                      if (isSourceError) {
                        const resolverSource = pickRecoverySource(
                          video.currentSrc || video.src || '',
                          config.videoUrl,
                          config.originalVideoUrl ?? null
                        );
                        if (!isHttpUrl(resolverSource)) {
                          const baseMsg = resolveVideoErrorMessage(video, error);
                          const finalMessage =
                            isSourceError && !config.originalVideoUrl
                              ? `${baseMsg} This source is not GitHub-hosted yet — open Upload and host it in cloud.`
                              : baseMsg;
                          setVideoError(finalMessage);
                          reportDiagnostic({
                            eventType: 'study_video_playback_failed',
                            severity: 'error',
                            errorCode: 'unsupported_source',
                            message: finalMessage,
                            context: {
                              candidate_url: video.currentSrc || video.src || null,
                              source_error: isSourceError
                            },
                            dedupeKey: `study_video_playback_failed:play_click:${finalMessage}:${video.currentSrc || video.src || ''}`
                          });
                          return;
                        }
                        try {
                          const response = await fetch('/api/video/resolve', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ url: resolverSource })
                          });
                          const body = (await response.json().catch(() => null)) as { videoUrl?: string } | null;
                          const freshUrl = body?.videoUrl?.trim() ?? '';
                          const canUseFreshUrl =
                            freshUrl.length > 0 &&
                            (!isDefaultStudyWithPinnedFallback || !looksLikeHlsUrl(freshUrl));
                          if (canUseFreshUrl) {
                            setConfig((prev) => ({ ...prev, videoUrl: freshUrl }));
                            const refreshedReady = await ensurePlayableSource(video, freshUrl);
                            if (refreshedReady) {
                              await video.play();
                              setVideoError(null);
                              reportDiagnostic({
                                eventType: 'study_video_playback_recovered',
                                severity: 'info',
                                errorCode: 'play_click_resolver_recovery',
                                message: 'Playback recovered after resolver URL refresh during play.',
                                context: {
                                  resolver_source: resolverSource,
                                  refreshed_url: freshUrl
                                },
                                dedupeKey: `study_video_playback_recovered:play_click_resolver:${freshUrl}`
                              });
                              return;
                            }
                          }
                        } catch {
                          // Fall through to show error.
                        }
                      }
                      const baseMsg = resolveVideoErrorMessage(video, error);
                      const finalMessage =
                        isSourceError && !config.originalVideoUrl
                          ? `${baseMsg} This source is not GitHub-hosted yet — open Upload and host it in cloud.`
                          : baseMsg;
                      setVideoError(finalMessage);
                      reportDiagnostic({
                        eventType: 'study_video_playback_failed',
                        severity: 'error',
                        errorCode: isSourceError ? 'unsupported_source' : 'playback_start_failed',
                        message: finalMessage,
                        context: {
                          candidate_url: video.currentSrc || video.src || null,
                          source_error: isSourceError
                        },
                        dedupeKey: `study_video_playback_failed:play_click:${finalMessage}:${video.currentSrc || video.src || ''}`
                      });
                    });
                }}
                data-testid="play-button"
              >
                {isPlaying ? 'Playing' : 'Play'}
              </button>
              <button
                onClick={() => {
                  studyVideoRef.current?.pause();
                }}
                data-testid="pause-button"
              >
                Pause
              </button>
              <button onClick={finishEarlyAndUpload} data-testid="end-early-button">
                End session early
              </button>
            </div>

            <p>
              videoTimeMs: <strong data-testid="video-time-ms">{videoTimeMs}</strong>
            </p>
            {videoError ? <p className="status-bad">{videoError}</p> : null}
          </section>
        ) : null}

        {stage === 'annotation' ? (
          <StudyAnnotation
            videoElement={
              <video
                ref={studyVideoRef}
                controls
                preload="auto"
                playsInline
                className="immersive-video"
                onPlay={() => {
                  setIsPlaying(true);
                  videoTimeTrackerRef.current.setPlaybackState({ isPlaying: true, isBuffering: false });
                  syncClockFromVideo(false);
                  appendEvent('play', { mode: 'annotation' });
                }}
                onPause={() => {
                  setIsPlaying(false);
                  videoTimeTrackerRef.current.setPlaybackState({ isPlaying: false, isBuffering: false });
                  syncClockFromVideo(false);
                  appendEvent('pause', { mode: 'annotation' });
                }}
                onSeeking={() => {
                  onVideoSeeking('annotation');
                }}
                onSeeked={() => {
                  onVideoSeeked('annotation');
                }}
                onVolumeChange={() => {
                  onVideoVolumeChange('annotation');
                }}
                onRateChange={(event) => {
                  videoTimeTrackerRef.current.setPlaybackState({
                    playbackRate: event.currentTarget.playbackRate
                  });
                  syncClockFromVideo(false);
                }}
                onWaiting={() => {
                  videoTimeTrackerRef.current.setPlaybackState({ isBuffering: true });
                  syncClockFromVideo(false);
                }}
                onStalled={() => {
                  videoTimeTrackerRef.current.setPlaybackState({ isBuffering: true });
                  syncClockFromVideo(false);
                }}
                onPlaying={() => {
                  videoTimeTrackerRef.current.setPlaybackState({ isBuffering: false, isPlaying: true });
                  syncClockFromVideo(false);
                }}
                onEnded={() => {
                  setIsPlaying(false);
                  videoTimeTrackerRef.current.setPlaybackState({ isPlaying: false, isBuffering: false });
                  syncClockFromVideo(false);
                  appendEvent('ended', { mode: 'annotation' });
                }}
                onLoadedMetadata={(event) => {
                  const durationMs = Number.isFinite(event.currentTarget.duration)
                    ? Math.round(event.currentTarget.duration * 1000)
                    : 0;
                  setAnnotationDurationMs(Math.max(durationMs, 0));
                  event.currentTarget.currentTime = 0;
                  setAnnotationCursorMs(0);
                  syncClockFromVideo(true);
                }}
                onTimeUpdate={(event) => {
                  const currentMs = Math.max(0, Math.round(event.currentTarget.currentTime * 1000));
                  setAnnotationCursorMs(currentMs);
                  if (!isPlaying) {
                    syncClockFromVideo(true);
                  }
                }}
                onLoadedData={() => {
                  setVideoError(null);
                  const video = studyVideoRef.current;
                  isMutedRef.current = video ? video.muted || video.volume === 0 : false;
                  lastVolumeRef.current = video?.volume ?? 1;
                }}
                onError={(event) => {
                  const target = event.currentTarget;
                  void (async () => {
                    const candidateUrl = target.currentSrc || target.src || '';
                    const recoverySource = (config.originalVideoUrl?.trim() || candidateUrl).trim();
                    const hostedUrl = await hostVideoInCloud(recoverySource);
                    if (hostedUrl && studyVideoRef.current) {
                      const recovered = await ensurePlayableSource(studyVideoRef.current, hostedUrl);
                      if (recovered) {
                        setVideoError(null);
                        return;
                      }
                    }
                    setVideoError(resolveVideoErrorMessage(target));
                  })();
                }}
                data-testid="annotation-video"
              />
            }
            annotationCursorMs={annotationCursorMs}
            annotationDurationMs={annotationDurationMs}
            annotationMarkers={annotationMarkers}
            annotationNoteDraft={annotationNoteDraft}
            markerCounts={markerCounts}
            dialModeEnabled={dialModeEnabled}
            dialValue={dialValue}
            dialSampleCount={dialSampleCount}
            dialEnabled={config.dialEnabled}
            firstPassEnded={firstPassEnded}
            nextStudyHref={nextStudyHref}
            nextStudyTitle={nextStudyTitle}
            videoError={videoError}
            setAnnotationNoteDraft={setAnnotationNoteDraft}
            seekAnnotationTimeline={seekAnnotationTimeline}
            addMarker={addMarker}
            removeMarker={removeMarker}
            onSkipAnnotation={() => {
              annotationSkippedRef.current = true;
              setAnnotationSkipped(true);
              appendEvent('annotation_mode_skipped', { explicitSkip: true });
              toSurveyStage();
            }}
            onContinueToSurvey={() => {
              annotationSkippedRef.current = false;
              setAnnotationSkipped(false);
              toSurveyStage();
            }}
            setDialModeEnabled={setDialModeEnabled}
            setDialValue={(value: number) => {
              setDialValue(value);
              dialValueRef.current = value;
            }}
            appendEvent={appendEvent}
          />
        ) : null}

        {stage === 'survey' ? (
          <StudySurvey
            surveyOverallEngagement={surveyOverallEngagement}
            surveyContentClarity={surveyContentClarity}
            surveyAdditionalComments={surveyAdditionalComments}
            canFinishSession={canFinishSession}
            setSurveyOverallEngagement={setSurveyOverallEngagement}
            setSurveyContentClarity={setSurveyContentClarity}
            setSurveyAdditionalComments={setSurveyAdditionalComments}
            finishAndUpload={finishAndUpload}
          />
        ) : null}

        {(stage === 'next_video' || stage === 'complete') ? (
          <StudyCompletion
            stage={stage}
            nextStudyHref={nextStudyHref}
            nextStudyTitle={nextStudyTitle}
            nextVideoChoice={nextVideoChoice}
            annotationMarkers={annotationMarkers}
            dialSampleCount={dialSampleCount}
            timeline={timeline}
            setStage={setStage}
          />
        ) : null}

        <section className="panel stack">
          {uploadStatus ? <p data-testid="upload-status">{uploadStatus}</p> : null}
          {dashboardUrl ? (
            <p data-testid="dashboard-link">
              Open timeline dashboard:{' '}
              <a href={dashboardUrl} target="_blank" rel="noreferrer">
                {dashboardUrl}
              </a>
            </p>
          ) : null}
        </section>
      </div>
    </main>
  );
}
