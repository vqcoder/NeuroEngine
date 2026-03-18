'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  type DialSample,
  type SurveyResponse,
  uploadPayloadSchema
} from '@/lib/schema';
import { VideoTimeTracker } from '@/lib/videoClock';
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
  type MarkerType,
  DEFAULT_QUALITY,
  emptyConfig
} from '@/lib/studyTypes';
import {
  saveParticipantInfo,
  readParticipantInfo,
  safeUuid,
  maybeUuid,
  parseSurveyScore,
  isPlaybackTelemetryStage,
  applyCanonicalLibraryParams,
  looksLikeWebPageUrl,
  unwrapHlsProxySourceUrl,
  looksLikeHlsUrl,
  toHlsProxyUrl,
  getDefaultStudyFallbackUrl,
  isGithubHostedVideoUrl,
  mapToProxyAssetUrl,
  normalizeLegacyAssetUrl
} from '@/lib/studyHelpers';
import { buildSurveyAnalyticsHighlights } from '@/lib/surveyAnalytics';
import StudyOnboarding from './components/StudyOnboarding';
import StudyCameraCheck from './components/StudyCameraCheck';
import StudyAnnotation from './components/StudyAnnotation';
import StudySurvey from './components/StudySurvey';
import StudyCompletion from './components/StudyCompletion';
import { useTimeline } from './hooks/useTimeline';
import { useWebcam } from './hooks/useWebcam';
import { useSessionUpload } from './hooks/useSessionUpload';


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
  const [webcamBypassed, setWebcamBypassed] = useState(false);

  const [isPlaying, setIsPlaying] = useState(false);
  const [videoCompleted, setVideoCompleted] = useState(false);
  const [firstPassEnded, setFirstPassEnded] = useState(false);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [endingEarly, setEndingEarly] = useState(false);
  const endedEarlyRef = useRef<{ lastVideoTimeMs: number } | null>(null);
  const [nextStudyHref, setNextStudyHref] = useState<string | null>(null);
  const [nextStudyTitle, setNextStudyTitle] = useState<string | null>(null);
  const [nextVideoChoice, setNextVideoChoice] = useState<{ item: VideoLibraryItem; href: string } | null>(null);

  const [dialModeEnabled, setDialModeEnabled] = useState(false);
  const [dialValue, setDialValue] = useState(50);
  const [dialSampleCount, setDialSampleCount] = useState(0);

  const [audioCheckPlayed, setAudioCheckPlayed] = useState(false);
  const [audioConfirmed, setAudioConfirmed] = useState(false);

  const [annotationNoteDraft, setAnnotationNoteDraft] = useState('');
  const [annotationCursorMs, setAnnotationCursorMs] = useState(0);
  const [annotationDurationMs, setAnnotationDurationMs] = useState(0);

  const [surveyOverallEngagement, setSurveyOverallEngagement] = useState('');
  const [surveyContentClarity, setSurveyContentClarity] = useState('');
  const [surveyAdditionalComments, setSurveyAdditionalComments] = useState('');

  // Shared refs that hooks depend on
  const studyVideoRef = useRef<HTMLVideoElement | null>(null);
  const videoTimeTrackerRef = useRef(new VideoTimeTracker());
  const monotonicClientTimeRef = useRef(0);
  const lastObservedVideoTimeRef = useRef(0);
  const stageRef = useRef<StudyStage>('onboarding');

  const isMutedRef = useRef(false);
  const lastVolumeRef = useRef(1);
  const seekStartVideoTimeRef = useRef<number | null>(null);
  const dialSampleTimerRef = useRef<number | null>(null);
  const dialValueRef = useRef(dialValue);
  const hlsPlayerRef = useRef<{ destroy: () => void } | null>(null);
  const hlsSourceBoundRef = useRef<string | null>(null);
  const cloudHostingInFlightRef = useRef(false);
  const cloudHostingAttemptedRef = useRef(new Set<string>());
  const hlsRecoveryAttemptedRef = useRef(new Map<string, number>());
  const diagnosticDedupeRef = useRef(new Set<string>());
  const defaultStudyFallbackUrl = getDefaultStudyFallbackUrl(studyId);
  const isDefaultStudyWithPinnedFallback =
    Boolean(defaultStudyFallbackUrl) && !looksLikeHlsUrl(defaultStudyFallbackUrl ?? '');

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

  // ── Hook: useTimeline ────────────────────────────────────────────────────
  const {
    timeline, annotationMarkers, annotationSkipped, videoTimeMs,
    timelineRef, annotationMarkersRef, annotationSkippedRef, dialSamplesRef,
    appendEvent, appendAbandonmentEvent, addAnnotationMarker, removeAnnotationMarker,
    createTimelineEvent, sampleSyncedVideoTimeMs,
    setAnnotationMarkers, setAnnotationSkipped, setVideoTimeMs,
  } = useTimeline({
    studyId,
    sessionId,
    videoId: config.videoId,
    videoTimeTrackerRef,
    studyVideoRef,
    monotonicClientTimeRef,
    lastObservedVideoTimeRef,
    stageRef,
  });

  // ── Hook: useWebcam ──────────────────────────────────────────────────────
  const {
    webcamStatus, quality, capturedFrameCount,
    streamRef, webcamVideoRef, captureCanvasRef, qualityCanvasRef,
    framesRef, framePointersRef, qualitySamplesRef, frameCounterRef,
    startWebcamChecks, stopWebcamCaptureLoops, startFrameCapture,
    bypassWebcam, stopWebcam, startFrameCounter,
    setWebcamStatus, setQuality, setCapturedFrameCount,
    resetQualityBuffers,
  } = useWebcam({
    appendEvent,
    sampleSyncedVideoTimeMs,
    stageRef,
    requireWebcam: config.requireWebcam,
  });

  // ── Hook: useSessionUpload ───────────────────────────────────────────────
  const {
    uploadStatus, dashboardUrl, uploadTriggeredRef,
    uploadSession, setUploadStatus, buildPayload,
  } = useSessionUpload({
    studyId,
    participantId,
    participantName,
    participantEmail,
    sessionId,
    videoId: config.videoId,
    resolveUploadSourceUrl,
    timelineRef,
    framesRef,
    framePointersRef,
    dialSamplesRef,
    qualitySamplesRef,
    annotationMarkersRef,
    annotationSkippedRef,
    sampleSyncedVideoTimeMs,
    appendEvent,
    annotationDurationMs,
    setStage,
    setNextVideoChoice,
  });

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
    // Scroll to top when entering an immersive stage so the video is visible.
    if (stage === 'watch' || stage === 'annotation') {
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }, [stage]);


  useEffect(() => {
    dialValueRef.current = dialValue;
  }, [dialValue]);

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

  const stopDialSampling = () => {
    if (dialSampleTimerRef.current !== null) {
      window.clearInterval(dialSampleTimerRef.current);
      dialSampleTimerRef.current = null;
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
    resetQualityBuffers();
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
    resetQualityBuffers();
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
    resetQualityBuffers();
    await startWebcamChecks();
  };

  const onContinueWithoutWebcam = () => {
    bypassWebcam();
    setWebcamBypassed(true);
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
    addAnnotationMarker(markerType, annotationNoteDraft, getCurrentAnnotationTimeMs);
    setAnnotationNoteDraft('');
  };

  const removeMarker = (markerId: string) => {
    removeAnnotationMarker(markerId);
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

  const finishAndUpload = async () => {
    if (overallEngagementScore === null || contentClarityScore === null) {
      setUploadStatus('Enter both scores as whole numbers between 1 and 5 before finishing.');
      return;
    }

    try {
      setUploadStatus('Uploading...');

      const earlyEnd = endedEarlyRef.current;

      appendEvent('survey_answered', {
        markerCount: annotationMarkersRef.current.length,
        annotationSkipped: annotationSkippedRef.current,
        overallEngagement: overallEngagementScore,
        contentClarity: contentClarityScore,
        hasComment: surveyAdditionalComments.trim().length > 0,
        endedEarly: earlyEnd !== null
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
          responseJson: earlyEnd
            ? {
                status: 'incomplete',
                reason: 'user_ended_early',
                session_id: sessionId,
                last_video_time_ms: earlyEnd.lastVideoTimeMs
              }
            : {
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
    } catch (error) {
      console.error('[finishAndUpload] Unexpected error:', error);
      setUploadStatus(
        `Upload failed: ${error instanceof Error ? error.message : 'Unexpected error during submission.'}`
      );
    }
  };

  const finishEarlyAndUpload = () => {
    if (endingEarly) return;
    setEndingEarly(true);

    // Pause video immediately.
    try {
      studyVideoRef.current?.pause();
    } catch { /* best-effort */ }

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

    // Remember that the session was ended early so finishAndUpload marks
    // the completion status as incomplete.
    endedEarlyRef.current = { lastVideoTimeMs: abandonmentVideoTimeMs };

    // Skip annotation, go straight to survey so the user can still rate.
    annotationSkippedRef.current = true;
    setAnnotationSkipped(true);
    toSurveyStage();
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

  const isImmersiveStage = stage === 'watch' || stage === 'annotation';

  return (
    <main style={isImmersiveStage ? { padding: '12px 24px' } : undefined}>
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

        {stage === 'watch' || stage === 'annotation' ? (
          <div className="panel" style={{ padding: '10px 24px' }}>
            <small>
              {config.title} · Session <code>{sessionId.slice(0, 8)}</code> ·{' '}
              Webcam: {webcamStatus === 'granted' ? (quality.pass ? '✓' : '⚠') : '—'} ·{' '}
              Tracking: {(quality.trackingConfidence * 100).toFixed(0)}% · Frames: {capturedFrameCount}
            </small>
          </div>
        ) : (
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
        )}

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
              <button onClick={finishEarlyAndUpload} disabled={endingEarly} data-testid="end-early-button">
                {endingEarly ? 'Ending session…' : 'End session early'}
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
            uploadStatus={uploadStatus}
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
