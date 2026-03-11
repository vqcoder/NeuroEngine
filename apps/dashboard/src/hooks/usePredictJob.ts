import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchPredictJobStatus,
  predictVideoFromFile,
  predictVideoFromUrl,
  reportFrontendDiagnosticFireAndForget
} from '../api';
import type { PredictJobStatus, PredictResponse } from '../types';
import {
  buildPlaybackCandidates,
  normalizePredictorInputUrl
} from '../utils/predictorTimeline';
import { isHttpUrl } from '../utils/videoDashboard';

export type PredictJobState = {
  loading: boolean;
  slowLoad: boolean;
  error: string | null;
  uploadGuide: string | null;
  jobStatus: PredictJobStatus | null;
  elapsed: number;
  predictResponse: PredictResponse | null;
  playbackCandidates: string[];
  playbackCandidateIndex: number;
  playbackError: string | null;
};

export type UsePredictJobReturn = PredictJobState & {
  onSubmit: (event: FormEvent, inputTab: 'url' | 'file', videoUrl: string, selectedFile: File | null) => Promise<void>;
  handleCancel: () => void;
  setUploadGuide: (value: string | null) => void;
  setPlaybackCandidateIndex: React.Dispatch<React.SetStateAction<number>>;
  setPlaybackError: (value: string | null) => void;
  reportPredictorDiagnostic: (params: {
    severity?: 'info' | 'warning' | 'error';
    eventType: string;
    errorCode?: string;
    message?: string;
    context?: Record<string, unknown>;
  }) => void;
  /** Callback to switch inputTab from within the hook (e.g. when platform blocks). */
  requestInputTabSwitch: ((tab: 'url' | 'file') => void) | null;
  setRequestInputTabSwitch: (fn: (tab: 'url' | 'file') => void) => void;
};

export function usePredictJob(): UsePredictJobReturn {
  const [loading, setLoading] = useState(false);
  const [slowLoad, setSlowLoad] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadGuide, setUploadGuide] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<PredictJobStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [predictResponse, setPredictResponse] = useState<PredictResponse | null>(null);
  const [playbackCandidates, setPlaybackCandidates] = useState<string[]>([]);
  const [playbackCandidateIndex, setPlaybackCandidateIndex] = useState(0);
  const [playbackError, setPlaybackError] = useState<string | null>(null);

  const jobStartedAtRef = useRef<number>(0);
  const elapsedIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Allow the page to register a callback so the hook can switch the input tab
  const inputTabSwitchRef = useRef<((tab: 'url' | 'file') => void) | null>(null);
  const setRequestInputTabSwitch = useCallback((fn: (tab: 'url' | 'file') => void) => {
    inputTabSwitchRef.current = fn;
  }, []);

  // Elapsed-time counter
  useEffect(() => {
    if (loading) {
      jobStartedAtRef.current = Date.now();
      setElapsed(0);
      elapsedIntervalRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - jobStartedAtRef.current) / 1000));
      }, 1000);
    } else {
      if (elapsedIntervalRef.current !== null) {
        clearInterval(elapsedIntervalRef.current);
        elapsedIntervalRef.current = null;
      }
    }
    return () => {
      if (elapsedIntervalRef.current !== null) {
        clearInterval(elapsedIntervalRef.current);
        elapsedIntervalRef.current = null;
      }
    };
  }, [loading]);

  // Unmount cleanup -- stop polling if user navigates away mid-prediction
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, []);

  const switchToFile = useCallback(() => {
    inputTabSwitchRef.current?.('file');
  }, []);

  const reportPredictorDiagnostic = useCallback(({
    severity = 'error',
    eventType,
    errorCode,
    message,
    context
  }: {
    severity?: 'info' | 'warning' | 'error';
    eventType: string;
    errorCode?: string;
    message?: string;
    context?: Record<string, unknown>;
  }) => {
    const route =
      typeof window !== 'undefined'
        ? `${window.location.pathname}${window.location.search}`
        : '/predictor';
    reportFrontendDiagnosticFireAndForget({
      surface: 'dashboard',
      page: 'predictor',
      route,
      severity,
      event_type: eventType,
      ...(errorCode ? { error_code: errorCode } : {}),
      ...(message ? { message } : {}),
      context: {
        ...(context ?? {})
      }
    });
  }, []);

  const handleCancel = useCallback(() => {
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setLoading(false);
    setSlowLoad(false);
    setJobStatus(null);
    setElapsed(0);
  }, []);

  const onSubmit = useCallback(async (
    event: FormEvent,
    inputTab: 'url' | 'file',
    videoUrl: string,
    selectedFile: File | null
  ) => {
    event.preventDefault();

    // Clear any previous polling interval
    if (pollIntervalRef.current !== null) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    setLoading(true);
    setSlowLoad(false);
    setError(null);
    setPredictResponse(null);
    setJobStatus(null);
    setPlaybackCandidates([]);
    setPlaybackCandidateIndex(0);
    setPlaybackError(null);

    // Input validation (runs synchronously before the network call)
    let normalizedInputUrl = '';
    if (inputTab === 'file') {
      if (!selectedFile) {
        setError('Select a video file to upload.');
        setLoading(false);
        return;
      }
      const MAX_FILE_BYTES = 500 * 1024 * 1024; // 500 MB
      if (selectedFile.size > MAX_FILE_BYTES) {
        setError(`File is too large (${(selectedFile.size / 1024 / 1024).toFixed(0)} MB). Maximum is 500 MB.`);
        setLoading(false);
        return;
      }
    } else {
      const trimmed = videoUrl.trim();
      normalizedInputUrl = normalizePredictorInputUrl(trimmed);
      if (!isHttpUrl(normalizedInputUrl)) {
        setError('Enter a valid http(s) video URL.');
        setLoading(false);
        return;
      }
      // Pre-block platforms that require auth to download (yt-dlp cannot help regardless).
      // YouTube is handled server-side with cookies if YOUTUBE_COOKIES_NETSCAPE is configured.
      const isAuthWalledPlatform = /tiktok\.com|instagram\.com|twitter\.com|x\.com|facebook\.com|fb\.watch/i.test(trimmed);
      if (isAuthWalledPlatform) {
        setUploadGuide('This platform requires login to download videos. Download the video file locally, then upload it using the Upload File tab.');
        switchToFile();
        reportPredictorDiagnostic({
          severity: 'warning',
          eventType: 'prediction_url_blocked',
          errorCode: 'platform_blocked',
          message: 'Predictor URL input blocked — platform requires authentication.',
          context: { input_url: normalizedInputUrl }
        });
        setLoading(false);
        return;
      }
    }

    // Kick off the job -- POST /predict returns immediately with a job_id
    let initialStatus: PredictJobStatus;
    try {
      if (inputTab === 'file') {
        initialStatus = await predictVideoFromFile(selectedFile!);
        // Provide a local object URL for playback while the job runs
        setPlaybackCandidates([URL.createObjectURL(selectedFile!)]);
      } else {
        initialStatus = await predictVideoFromUrl(normalizedInputUrl);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Prediction failed.';
      const isPlatformBlock = msg.includes('blocks server-side') || msg.includes('platform that blocks');
      const isRateLimit = msg.includes('rate-limit') || msg.includes('429') || msg.includes('Too Many Requests');
      const isYouTubeBlock = msg.includes('YouTube blocks') || msg.includes('youtube') || msg.toLowerCase().includes('youtube');
      if (isPlatformBlock || isRateLimit || isYouTubeBlock) {
        setUploadGuide(
          isYouTubeBlock || isRateLimit
            ? 'YouTube blocks server-side downloads. Download the video file locally (e.g. via yt-dlp or a browser extension), then upload it using the Upload File tab.'
            : 'This platform requires authentication to download. Download the video file locally, then upload it using the Upload File tab.'
        );
        switchToFile();
      } else {
        setError(msg);
      }
      reportPredictorDiagnostic({
        severity: 'error',
        eventType: 'prediction_request_failed',
        errorCode: isPlatformBlock ? 'platform_blocked' : 'prediction_failed',
        message: msg
      });
      setLoading(false);
      return;
    }

    setJobStatus(initialStatus);

    // If the job already finished (e.g. cached result), handle it immediately
    const handleTerminalStatus = (status: PredictJobStatus) => {
      if (status.status === 'done' && status.result) {
        const payload = status.result;
        setPredictResponse(payload);
        if (!payload.predictions.length) {
          setError('Prediction finished, but no trace points were returned.');
          reportPredictorDiagnostic({
            severity: 'warning',
            eventType: 'prediction_empty_trace',
            errorCode: 'empty_predictions',
            message: 'Predict endpoint completed without returning prediction points.'
          });
        }
        if (inputTab === 'url') {
          const resolvedVideoUrl = payload.resolved_video_url?.trim() || '';
          setPlaybackCandidates(buildPlaybackCandidates(resolvedVideoUrl, normalizedInputUrl));
        }
      } else if (status.status === 'failed') {
        const msg = status.error || 'Prediction failed.';
        const isRateLimit = msg.includes('rate-limit') || msg.includes('429') || msg.includes('Too Many Requests');
        const isYouTubeBlock = msg.toLowerCase().includes('youtube') || msg.includes('bot-detection');
        if (isRateLimit || isYouTubeBlock) {
          setUploadGuide('YouTube blocks server-side downloads. Download the video file locally (e.g. via yt-dlp or a browser extension), then upload it using the Upload File tab.');
          switchToFile();
        } else {
          setError(msg);
        }
        reportPredictorDiagnostic({
          severity: 'error',
          eventType: 'prediction_request_failed',
          errorCode: isRateLimit || isYouTubeBlock ? 'youtube_blocked' : 'prediction_failed',
          message: msg
        });
      }
      setSlowLoad(false);
      setLoading(false);
    };

    if (initialStatus.status === 'done' || initialStatus.status === 'failed') {
      handleTerminalStatus(initialStatus);
      return;
    }

    // Start polling every 2 seconds
    const slowLoadTimer = setTimeout(() => setSlowLoad(true), 30_000);
    const jobId = initialStatus.job_id;

    pollIntervalRef.current = setInterval(async () => {
      try {
        const status = await fetchPredictJobStatus(jobId);
        setJobStatus(status);
        if (status.status === 'done' || status.status === 'failed') {
          clearInterval(pollIntervalRef.current!);
          pollIntervalRef.current = null;
          clearTimeout(slowLoadTimer);
          handleTerminalStatus(status);
        }
      } catch {
        // Network hiccup -- keep polling; transient errors shouldn't abort the job
      }
    }, 2000);
  }, [reportPredictorDiagnostic, switchToFile]);

  return {
    loading,
    slowLoad,
    error,
    uploadGuide,
    jobStatus,
    elapsed,
    predictResponse,
    playbackCandidates,
    playbackCandidateIndex,
    playbackError,
    onSubmit,
    handleCancel,
    setUploadGuide,
    setPlaybackCandidateIndex,
    setPlaybackError,
    reportPredictorDiagnostic,
    requestInputTabSwitch: inputTabSwitchRef.current,
    setRequestInputTabSwitch
  };
}
