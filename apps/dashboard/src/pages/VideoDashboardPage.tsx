import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  FormGroup,
  Grid,
  List,
  ListItem,
  ListItemText,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import NeuroScorecards from '../components/NeuroScorecards';
import ProductRollupPanel from '../components/ProductRollupPanel';
import SummaryChart from '../components/SummaryChart';
import { TermTooltip } from '../components/TermTooltip';
import {
  fetchVideoReadout,
  fetchVideoReadoutExportPackage,
  predictVideoFromUrlAwait,
  reportFrontendDiagnosticFireAndForget
} from '../api';
import type {
  AnnotationOverlayMarker,
  PlaybackTelemetryEvent,
  PredictTracePoint,
  TelemetryOverlayMarker,
  TimestampSummary,
  ReadoutDiagnosticCard,
  TraceLayerVisibility,
  VideoReadout
} from '../types';
import { exportReadoutCsv, exportReadoutJson, exportReadoutPackage } from '../utils/exporters';
import { mapReadoutToTimeline } from '../utils/readout';
import {
  SAMPLE_VIDEO_URL,
  DEFAULT_WINDOW_MS,
  asUuidOrUndefined,
  mergeMeasuredAndPredictedTimeline,
  isHttpUrl,
  buildVideoSourceCandidates,
  resolvePredictionSourceUrl,
  normalizeSeekSeconds,
  formatSurveyScore,
  formatIndexScore,
  formatTraceSource,
  normalizeIndexToSignedSynchrony,
  isFiniteSynchrony
} from '../utils/videoDashboard';
import {
  MARKER_DISPLAY_LABEL,
  TELEMETRY_KIND_LABEL,
  type ReliabilityComponentKey,
  RELIABILITY_COMPONENTS,
  TRACE_LEGEND_ITEMS,
  OVERLAY_LEGEND_ITEMS,
  DEFAULT_TRACE_LAYER_VISIBILITY,
  TRACE_LAYER_OPTIONS,
  DIAGNOSTIC_CARD_ORDER,
  DIAGNOSTIC_CARD_META,
  ACCORDION_BASE_SX,
  toTelemetryOverlayKind,
  SectionLabel,
  SegmentPanel
} from './videoDashboardConstants';
import RetryAlert from '../components/RetryAlert';
import SignalDiagnosticsSection from './SignalDiagnosticsSection';

export default function VideoDashboardPage() {
  const navigate = useNavigate();
  const { videoId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const predictionCacheRef = useRef<Map<string, { model: string; points: PredictTracePoint[] }>>(
    new Map()
  );
  const pendingSeekRef = useRef<number | null>(null);

  const [readout, setReadout] = useState<VideoReadout | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [predictionModel, setPredictionModel] = useState<string | null>(null);
  const [predictionPoints, setPredictionPoints] = useState<PredictTracePoint[]>([]);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [predictionUrlApplied, setPredictionUrlApplied] = useState<string | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [videoSourceCandidates, setVideoSourceCandidates] = useState<string[]>([SAMPLE_VIDEO_URL]);
  const [activeVideoSourceIndex, setActiveVideoSourceIndex] = useState(0);
  const [videoPlaybackError, setVideoPlaybackError] = useState<string | null>(null);
  const [exportingPackage, setExportingPackage] = useState(false);
  const videoSrc =
    videoSourceCandidates[Math.min(activeVideoSourceIndex, Math.max(0, videoSourceCandidates.length - 1))] ??
    SAMPLE_VIDEO_URL;

  const reportReadoutDiagnostic = ({
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
        : `/videos/${encodeURIComponent(videoId)}`;
    const diagnosticVideoId = asUuidOrUndefined(normalizedVideoId);
    reportFrontendDiagnosticFireAndForget({
      surface: 'dashboard',
      page: 'readout',
      route,
      severity,
      event_type: eventType,
      ...(errorCode ? { error_code: errorCode } : {}),
      ...(message ? { message } : {}),
      ...(diagnosticVideoId ? { video_id: diagnosticVideoId } : {}),
      context: {
        aggregate: aggregateApplied,
        session_id: sessionApplied ?? null,
        variant_id: variantApplied ?? null,
        window_ms: windowMsApplied,
        ...(context ?? {})
      }
    });
  };

  const initialAggregate =
    (searchParams.get('aggregate') ?? '').toLowerCase() === 'false' ? false : true;
  const initialSession =
    (searchParams.get('session_id') ?? searchParams.get('sessionId') ?? '').trim();
  const initialVariant =
    (searchParams.get('variant_id') ?? searchParams.get('variantId') ?? '').trim();
  const initialWindowParsed = Number(
    searchParams.get('window_ms') ?? searchParams.get('windowMs') ?? DEFAULT_WINDOW_MS
  );
  const initialWindow =
    Number.isFinite(initialWindowParsed) && initialWindowParsed > 0
      ? Math.round(initialWindowParsed)
      : DEFAULT_WINDOW_MS;

  const [aggregateDraft, setAggregateDraft] = useState(initialAggregate);
  const [sessionDraft, setSessionDraft] = useState(initialSession);
  const [variantDraft, setVariantDraft] = useState(initialVariant);
  const [windowMsDraft, setWindowMsDraft] = useState(initialWindow);
  const [aggregateApplied, setAggregateApplied] = useState(initialAggregate);
  const [sessionApplied, setSessionApplied] = useState<string | undefined>(
    initialSession || undefined
  );
  const [variantApplied, setVariantApplied] = useState<string | undefined>(
    initialVariant || undefined
  );
  const [windowMsApplied, setWindowMsApplied] = useState(initialWindow);
  const [traceLayersExpanded, setTraceLayersExpanded] = useState(false);
  const [showPredictedOverlay, setShowPredictedOverlay] = useState(false);

  const [layerVisibility, setLayerVisibility] = useState<TraceLayerVisibility>(DEFAULT_TRACE_LAYER_VISIBILITY);
  const [selectedAuNames, setSelectedAuNames] = useState<string[]>([]);
  const normalizedVideoId = useMemo(() => {
    try {
      return decodeURIComponent(videoId).trim();
    } catch {
      return videoId.trim();
    }
  }, [videoId]);
  const videoIdLooksLikeUrl = useMemo(
    () => normalizedVideoId.length > 0 && isHttpUrl(normalizedVideoId),
    [normalizedVideoId]
  );

  // ── Effects ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!videoIdLooksLikeUrl) {
      return;
    }
    const params = new URLSearchParams({
      video_url: normalizedVideoId
    });
    navigate(`/predictor?${params.toString()}`, { replace: true });
  }, [navigate, normalizedVideoId, videoIdLooksLikeUrl]);

  // Extracted so the retry button can re-invoke it.
  const loadReadout = useCallback(async () => {
    if (videoIdLooksLikeUrl || !normalizedVideoId) {
      setReadout(null);
      setLoading(false);
      setError(videoIdLooksLikeUrl ? null : 'Missing video ID.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = await fetchVideoReadout(normalizedVideoId, {
        aggregate: aggregateApplied,
        session_id: aggregateApplied ? undefined : sessionApplied,
        variant_id: variantApplied,
        window_ms: windowMsApplied
      });
      setReadout(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load readout';
      setError(message);
      reportReadoutDiagnostic({
        severity: 'error',
        eventType: 'readout_fetch_failed',
        errorCode: 'readout_fetch_failed',
        message
      });
    } finally {
      setLoading(false);
    }
  }, [aggregateApplied, normalizedVideoId, sessionApplied, variantApplied, videoIdLooksLikeUrl, windowMsApplied]);

  useEffect(() => {
    loadReadout();
  }, [loadReadout]);

  useEffect(() => {
    let cancelled = false;

    async function loadPredictionOverlay() {
      if (!readout) {
        setPredictionModel(null);
        setPredictionPoints([]);
        setPredictionError(null);
        setPredictionLoading(false);
        return;
      }

      const sourceUrl = (predictionUrlApplied ?? '').trim();
      if (!sourceUrl) {
        setPredictionModel(null);
        setPredictionPoints([]);
        const message =
          'Prediction overlay unavailable: no reachable source URL is attached to this readout.';
        setPredictionError(message);
        reportReadoutDiagnostic({
          severity: 'warning',
          eventType: 'readout_prediction_overlay_skipped',
          errorCode: 'missing_source_url',
          message
        });
        setPredictionLoading(false);
        return;
      }

      if (!isHttpUrl(sourceUrl)) {
        setPredictionModel(null);
        setPredictionPoints([]);
        const message = 'Prediction overlay URL must use http or https.';
        setPredictionError(message);
        reportReadoutDiagnostic({
          severity: 'warning',
          eventType: 'readout_prediction_overlay_skipped',
          errorCode: 'invalid_source_url',
          message,
          context: { prediction_url: sourceUrl }
        });
        setPredictionLoading(false);
        return;
      }

      const cached = predictionCacheRef.current.get(sourceUrl);
      if (cached) {
        setPredictionModel(cached.model);
        setPredictionPoints(cached.points);
        setPredictionError(null);
        setPredictionLoading(false);
        return;
      }

      setPredictionLoading(true);
      setPredictionError(null);
      try {
        const payload = await predictVideoFromUrlAwait(sourceUrl);
        if (cancelled) {
          return;
        }
        predictionCacheRef.current.set(sourceUrl, {
          model: payload.model_artifact,
          points: payload.predictions
        });
        setPredictionModel(payload.model_artifact);
        setPredictionPoints(payload.predictions);
      } catch (err) {
        if (cancelled) {
          return;
        }
        const message =
          err instanceof Error
            ? `Prediction overlay unavailable: ${err.message}`
            : 'Prediction overlay unavailable.';
        setPredictionModel(null);
        setPredictionPoints([]);
        setPredictionError(message);
        reportReadoutDiagnostic({
          severity: 'error',
          eventType: 'readout_prediction_overlay_failed',
          errorCode: 'prediction_overlay_failed',
          message,
          context: { prediction_url: sourceUrl }
        });
      } finally {
        if (!cancelled) {
          setPredictionLoading(false);
        }
      }
    }

    loadPredictionOverlay();
    return () => {
      cancelled = true;
    };
  }, [readout, predictionUrlApplied]);

  useEffect(() => {
    if (!readout) {
      return;
    }
    const available = readout.traces.au_channels.map((channel) => channel.au_name);
    if (selectedAuNames.length === 0) {
      setSelectedAuNames(available.slice(0, 3));
      return;
    }
    setSelectedAuNames((current) => current.filter((name) => available.includes(name)));
  }, [readout, selectedAuNames.length]);

  useEffect(() => {
    const sourceUrl = readout?.source_url?.trim() ?? '';
    const playbackCandidates = buildVideoSourceCandidates(sourceUrl);
    setVideoSourceCandidates(playbackCandidates);
    setActiveVideoSourceIndex(0);
    setVideoPlaybackError(null);
    setPredictionUrlApplied(resolvePredictionSourceUrl(sourceUrl, playbackCandidates));
  }, [readout]);

  // ── Derived state ───────────────────────────────────────────────────

  const timelinePoints = useMemo(() => {
    if (!readout) {
      return [];
    }
    const measured = mapReadoutToTimeline(readout);
    return mergeMeasuredAndPredictedTimeline(measured, predictionPoints);
  }, [predictionPoints, readout]);
  const chartScenes = useMemo(() => readout?.context.scenes ?? [], [readout]);
  const chartCuts = useMemo(() => readout?.context.cuts ?? [], [readout]);
  const chartCtaMarkers = useMemo(() => readout?.context.cta_markers ?? [], [readout]);
  const lowConfidenceWindows = useMemo(
    () =>
      (readout?.quality.low_confidence_windows ?? []).map((window) => ({
        startSec: window.start_video_time_ms / 1000,
        endSec: window.end_video_time_ms / 1000,
        qualityFlags: window.quality_flags ?? []
      })),
    [readout]
  );
  const availableAuNames = useMemo(
    () => readout?.traces.au_channels.map((channel) => channel.au_name) ?? [],
    [readout]
  );
  const qualitySummary = readout?.quality.session_quality_summary;
  const annotationSummary = readout?.labels.annotation_summary;
  const surveySummary = readout?.labels.survey_summary;
  const diagnosticsByType = useMemo(() => {
    const map = new Map<ReadoutDiagnosticCard['card_type'], ReadoutDiagnosticCard>();
    (readout?.diagnostics ?? []).forEach((item) => {
      map.set(item.card_type, item);
    });
    return map;
  }, [readout]);
  const annotationOverlays = useMemo<AnnotationOverlayMarker[]>(() => {
    if (!readout) {
      return [];
    }
    if (aggregateApplied) {
      return [...(annotationSummary?.marker_density ?? [])].sort(
        (a, b) => a.video_time_ms - b.video_time_ms
      );
    }
    return readout.labels.annotations
      .map((annotation) => ({
        marker_type: annotation.marker_type,
        video_time_ms: annotation.video_time_ms,
        count: 1,
        density: 1,
        scene_id: annotation.scene_id ?? null,
        cut_id: annotation.cut_id ?? null,
        cta_id: annotation.cta_id ?? null
      }))
      .sort((a, b) => a.video_time_ms - b.video_time_ms);
  }, [aggregateApplied, annotationSummary, readout]);

  const telemetryOverlays = useMemo<TelemetryOverlayMarker[]>(() => {
    if (!readout) {
      return [];
    }
    return (readout.playback_telemetry ?? [])
      .map((event: PlaybackTelemetryEvent): TelemetryOverlayMarker | null => {
        const kind = toTelemetryOverlayKind(event.event_type);
        if (!kind) {
          return null;
        }
        return {
          kind,
          video_time_ms: event.video_time_ms,
          count: 1,
          density: 1,
          scene_id: event.scene_id ?? null,
          cut_id: event.cut_id ?? null,
          cta_id: event.cta_id ?? null,
          event_types: [event.event_type]
        };
      })
      .filter((item): item is TelemetryOverlayMarker => item !== null)
      .sort((a, b) => a.video_time_ms - b.video_time_ms);
  }, [readout]);

  const telemetryCountByKind = useMemo(
    () =>
      telemetryOverlays.reduce(
        (acc, item) => {
          acc[item.kind] += item.count;
          return acc;
        },
        { pause: 0, seek: 0, abandonment: 0 } as Record<TelemetryOverlayMarker['kind'], number>
      ),
    [telemetryOverlays]
  );

  const abandonmentPoint = useMemo(() => {
    const candidates = telemetryOverlays.filter((item) => item.kind === 'abandonment');
    return candidates.length === 0 ? null : candidates[0];
  }, [telemetryOverlays]);

  // ── Handlers ────────────────────────────────────────────────────────

  const handleApplyFilters = () => {
    setError(null);
    if (!aggregateDraft && !sessionDraft.trim()) {
      setError('session_id is required when aggregate view is off.');
      return;
    }
    setAggregateApplied(aggregateDraft);
    setSessionApplied(aggregateDraft ? undefined : sessionDraft.trim());
    setVariantApplied(variantDraft.trim() || undefined);
    setWindowMsApplied(windowMsDraft);
  };

  const applySeek = (video: HTMLVideoElement, seconds: number): number | null => {
    const safeSeconds = normalizeSeekSeconds(seconds);
    if (safeSeconds === null) {
      return null;
    }
    const hasFiniteDuration = Number.isFinite(video.duration) && video.duration > 0;
    const maxSeconds = hasFiniteDuration ? Math.max(0, video.duration - 0.01) : safeSeconds;
    const targetSeconds = Math.min(safeSeconds, maxSeconds);
    try {
      video.currentTime = targetSeconds;
      return targetSeconds;
    } catch {
      return null;
    }
  };

  const flushPendingSeek = () => {
    const pending = pendingSeekRef.current;
    const video = videoRef.current;
    if (pending === null || !video) {
      return;
    }
    const applied = applySeek(video, pending);
    if (applied === null) {
      return;
    }
    pendingSeekRef.current = null;
    setCurrentSec(applied);
  };

  const handleVideoReady = () => {
    setVideoPlaybackError(null);
    flushPendingSeek();
  };

  const handleVideoPlaybackError = () => {
    setActiveVideoSourceIndex((currentIndex) => {
      if (currentIndex + 1 < videoSourceCandidates.length) {
        reportReadoutDiagnostic({
          severity: 'warning',
          eventType: 'readout_video_source_fallback',
          errorCode: 'candidate_failed',
          message: 'Video source candidate failed; moving to fallback source.',
          context: {
            failed_candidate_index: currentIndex,
            failed_candidate_url: videoSourceCandidates[currentIndex] ?? null,
            next_candidate_url: videoSourceCandidates[currentIndex + 1] ?? null
          }
        });
        return currentIndex + 1;
      }
      const message = 'Video playback failed for all available source URLs.';
      setVideoPlaybackError(message);
      reportReadoutDiagnostic({
        severity: 'error',
        eventType: 'readout_video_playback_failed',
        errorCode: 'all_candidates_failed',
        message,
        context: { playback_candidates: videoSourceCandidates }
      });
      return currentIndex;
    });
  };

  const handleSeek = (seconds: number) => {
    const safeSeconds = normalizeSeekSeconds(seconds);
    if (safeSeconds === null) {
      return;
    }
    const video = videoRef.current;
    if (!video) {
      pendingSeekRef.current = safeSeconds;
      setCurrentSec(safeSeconds);
      return;
    }
    const applied = applySeek(video, safeSeconds);
    if (applied === null) {
      pendingSeekRef.current = safeSeconds;
      setCurrentSec(safeSeconds);
      return;
    }
    pendingSeekRef.current = null;
    setCurrentSec(applied);
  };

  const toggleLayer = (key: keyof TraceLayerVisibility) => {
    setLayerVisibility((current) => ({ ...current, [key]: !current[key] }));
  };

  const toggleAu = (auName: string) => {
    setSelectedAuNames((current) =>
      current.includes(auName) ? current.filter((name) => name !== auName) : [...current, auName]
    );
  };

  const setAllTraceLayers = (enabled: boolean) => {
    setLayerVisibility((current) =>
      Object.keys(current).reduce((nextState, key) => {
        nextState[key as keyof TraceLayerVisibility] = enabled;
        return nextState;
      }, {} as TraceLayerVisibility)
    );
  };

  // ── Reliability computed values ─────────────────────────────────────

  const activeTraceLayerCount = Object.values(layerVisibility).filter(Boolean).length;
  const traceLayerSummaryLabel = `${activeTraceLayerCount}/${TRACE_LAYER_OPTIONS.length} traces on`;
  const auSummaryLabel = `${selectedAuNames.length}/${availableAuNames.length} AU on`;

  const qualityWarning = useMemo(() => {
    if (!qualitySummary) {
      return null;
    }
    if (qualitySummary.low_confidence_windows > 0) {
      return `Low-confidence windows: ${qualitySummary.low_confidence_windows}. Interpret webcam-derived traces cautiously.`;
    }
    return null;
  }, [qualitySummary]);

  const reliability = readout?.reliability_score ?? null;
  const reliabilityOverall = reliability?.overall ?? null;
  const reliabilityOverallColor: 'success' | 'warning' | 'error' | 'default' =
    reliabilityOverall === null
      ? 'default'
      : reliabilityOverall >= 99.95
        ? 'success'
        : reliabilityOverall >= 80
          ? 'warning'
          : 'error';
  const reliabilityComponentBreakdown = useMemo(() => {
    if (!reliability) {
      return [] as Array<{ key: ReliabilityComponentKey; label: string; weight: number; score: number }>;
    }
    return RELIABILITY_COMPONENTS.map((component) => ({
      ...component,
      score: Number(reliability[component.key] ?? 0)
    }));
  }, [reliability]);
  const reliabilityTopDeductions = useMemo(
    () =>
      reliabilityComponentBreakdown
        .filter((item) => item.score < 99.95)
        .sort((a, b) => a.score - b.score)
        .slice(0, 3),
    [reliabilityComponentBreakdown]
  );
  const reliabilitySupportIssues = useMemo(() => {
    if (!reliability) {
      return [] as string[];
    }
    const derivedDetails = (reliability.score_details ?? [])
      .filter(
        (detail) =>
          detail.status !== 'available' ||
          detail.issues.length > 0 ||
          detail.score_reliability < 0.95
      )
      .slice(0, 3)
      .map((detail) => {
        if (detail.issues.length > 0) {
          return `${detail.machine_name}: ${detail.issues[0]}`;
        }
        if (detail.status !== 'available') {
          return `${detail.machine_name}: status=${detail.status}.`;
        }
        return `${detail.machine_name}: score reliability ${(detail.score_reliability * 100).toFixed(0)}%.`;
      });
    const combined = [...(reliability.issues ?? []), ...derivedDetails]
      .map((item) => item.trim())
      .filter(Boolean);
    return [...new Set(combined)].slice(0, 5);
  }, [reliability]);
  const reliabilitySummary = useMemo(() => {
    if (!reliability || reliabilityOverall === null) {
      return 'Reliability score is unavailable for this readout.';
    }
    if (reliabilityOverall >= 99.95) {
      return `Reliability is ${reliabilityOverall.toFixed(1)}/100. All reliability checks passed.`;
    }
    if (reliabilityTopDeductions.length === 0) {
      return `Reliability is ${reliabilityOverall.toFixed(1)}/100. One or more checks are below full confidence.`;
    }
    const reasons = reliabilityTopDeductions
      .map((item) => `${item.label} ${item.score.toFixed(1)}`)
      .join(', ');
    return `Reliability is ${reliabilityOverall.toFixed(1)}/100. Not 100 because: ${reasons}.`;
  }, [reliability, reliabilityOverall, reliabilityTopDeductions]);
  const reliabilityAlertSeverity: 'success' | 'warning' | 'error' | 'info' =
    reliabilityOverall === null
      ? 'info'
      : reliabilityOverall >= 99.95
        ? 'success'
        : reliabilityOverall >= 80
          ? 'warning'
          : 'error';

  const aggregateMetrics = readout?.aggregate_metrics ?? null;
  const hasPredictionOverlay = predictionPoints.length > 0;
  const timelineReportPath = useMemo(() => {
    const params = new URLSearchParams();
    params.set('aggregate', String(aggregateApplied));
    if (!aggregateApplied && sessionApplied) {
      params.set('session_id', sessionApplied);
    }
    if (variantApplied) {
      params.set('variant_id', variantApplied);
    }
    params.set('window_ms', String(windowMsApplied));
    const suffix = params.toString();
    const basePath = `/videos/${encodeURIComponent(normalizedVideoId)}/timeline-report`;
    return suffix ? `${basePath}?${suffix}` : basePath;
  }, [aggregateApplied, normalizedVideoId, sessionApplied, variantApplied, windowMsApplied]);

  const handleExport = () => {
    if (!readout) {
      return;
    }
    exportReadoutCsv(readout, selectedAuNames);
    exportReadoutJson(readout);
  };

  const handleExportPackage = async () => {
    if (!readout || exportingPackage) {
      return;
    }
    setExportingPackage(true);
    try {
      const payload = await fetchVideoReadoutExportPackage(normalizedVideoId, {
        aggregate: aggregateApplied,
        session_id: aggregateApplied ? undefined : sessionApplied,
        variant_id: variantApplied,
        window_ms: windowMsApplied
      });
      exportReadoutPackage(readout.video_id, payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to export readout package';
      setError(message);
      reportReadoutDiagnostic({
        severity: 'error',
        eventType: 'readout_export_package_failed',
        errorCode: 'export_package_failed',
        message
      });
    } finally {
      setExportingPackage(false);
    }
  };

  const markerCountByType = (
    markerType: AnnotationOverlayMarker['marker_type']
  ): number => {
    if (!annotationSummary) {
      return 0;
    }
    switch (markerType) {
      case 'engaging_moment':
        return annotationSummary.engaging_moment_count;
      case 'confusing_moment':
        return annotationSummary.confusing_moment_count;
      case 'stop_watching_moment':
        return annotationSummary.stop_watching_moment_count;
      case 'cta_landed_moment':
        return annotationSummary.cta_landed_moment_count;
      default:
        return 0;
    }
  };

  const renderTopTimestampList = (
    items: TimestampSummary[],
    emptyLabel: string,
    jumpPrefix: string
  ) => {
    if (items.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary">
          {emptyLabel}
        </Typography>
      );
    }
    return (
      <List dense>
        {items.map((item, index) => (
          <ListItem
            key={`${jumpPrefix}-${item.video_time_ms}-${index}`}
            secondaryAction={
              <Button
                variant="text"
                size="small"
                onClick={() => handleSeek(item.video_time_ms / 1000)}
                data-testid={`${jumpPrefix}-jump-${index}`}
              >
                Seek
              </Button>
            }
          >
            <ListItemText
              primary={`${(item.video_time_ms / 1000).toFixed(1)}s`}
              secondary={[
                `count ${item.count}`,
                aggregateApplied ? `density ${item.density.toFixed(2)} / session` : null,
                item.scene_id ? `scene ${item.scene_id}` : null,
                item.cta_id ? `cta ${item.cta_id}` : null
              ]
                .filter(Boolean)
                .join(' • ')}
            />
          </ListItem>
        ))}
      </List>
    );
  };

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1500, mx: 'auto' }}>
      <Stack spacing={4}>

        {/* ─── HEADER ─── */}
        <Stack direction={{ xs: 'column', lg: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h4" fontWeight={700} data-testid="page-title">
              Readout Dashboard
            </Typography>
            <Typography color="text.secondary" variant="body2" mt={0.5}>
              Video ID: {normalizedVideoId || videoId}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip label={`${currentSec.toFixed(1)}s`} color="primary" data-testid="current-time-chip" />
            <Button variant="outlined" onClick={() => navigate(timelineReportPath)} data-testid="open-timeline-report-button">
              Timeline Report
            </Button>
            <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleExportPackage} disabled={!readout || exportingPackage} data-testid="export-package-button">
              {exportingPackage ? 'Exporting…' : 'Export Package'}
            </Button>
            <Button variant="contained" startIcon={<DownloadIcon />} onClick={handleExport} disabled={!readout} data-testid="export-button">
              Export Readout
            </Button>
          </Stack>
        </Stack>

        {/* ─── VIEW CONTROLS (collapsible) ─── */}
        <Card>
          <Accordion disableGutters sx={ACCORDION_BASE_SX}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Typography variant="subtitle2" fontWeight={700}>View Controls</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ pt: 0 }}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', md: 'center' }} flexWrap="wrap" useFlexGap>
                <FormControlLabel
                  control={<Switch checked={aggregateDraft} onChange={(event) => setAggregateDraft(event.target.checked)} data-testid="aggregate-switch" />}
                  label={aggregateDraft ? 'Aggregate View' : 'Single Session View'}
                />
                <TextField size="small" label="Session ID" value={sessionDraft} onChange={(event) => setSessionDraft(event.target.value)} disabled={aggregateDraft} inputProps={{ 'data-testid': 'session-id-filter' }} />
                <TextField size="small" label="Variant ID" value={variantDraft} onChange={(event) => setVariantDraft(event.target.value)} inputProps={{ 'data-testid': 'variant-id-filter' }} />
                <TextField size="small" label="Window (ms)" type="number" value={windowMsDraft} onChange={(event) => setWindowMsDraft(Number(event.target.value) || DEFAULT_WINDOW_MS)} inputProps={{ min: 100, max: 10000, step: 100, 'data-testid': 'window-ms-filter' }} />
                <Button variant="outlined" onClick={handleApplyFilters} data-testid="apply-filter-button">Apply</Button>
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Card>

        {loading ? (
          <Box sx={{ py: 8, textAlign: 'center' }}><CircularProgress /></Box>
        ) : null}

        {error ? <RetryAlert message={error} onRetry={loadReadout} /> : null}

        {!loading && !error && readout ? (
          <>
            <Box>
              <Card variant="outlined" data-testid="readout-reliability-card">
                <CardContent sx={{ py: 1.5 }}>
                  <Stack spacing={1}>
                    <Stack
                      direction={{ xs: 'column', sm: 'row' }}
                      spacing={1}
                      alignItems={{ xs: 'flex-start', sm: 'center' }}
                      flexWrap="wrap"
                      useFlexGap
                    >
                      <Typography variant="subtitle2" fontWeight={700}>Readout Reliability Score</Typography>
                      <Chip
                        label={reliabilityOverall === null ? 'n/a' : `${reliabilityOverall.toFixed(1)}/100`}
                        color={reliabilityOverallColor}
                        data-testid="readout-reliability-overall-chip"
                      />
                      {reliability ? (
                        <Chip
                          label={`Core scores ${reliability.scores_available}/${reliability.scores_total}`}
                          variant="outlined"
                          data-testid="readout-reliability-coverage-chip"
                        />
                      ) : null}
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Reliability rationale appears at the bottom of this readout.
                    </Typography>
                  </Stack>
                </CardContent>
              </Card>
            </Box>

            {/* ══════ SECTION 1 — Video + Live Trace ══════ */}
            <Box>
              <SectionLabel>01 — Video + Live Trace</SectionLabel>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, lg: 5 }}>
                  <Card sx={{ position: { lg: 'sticky' }, top: { lg: 16 } }}>
                    <CardContent>
                      <video
                        ref={videoRef}
                        src={videoSrc}
                        controls
                        width="100%"
                        style={{ borderRadius: 8, display: 'block' }}
                        onTimeUpdate={(event) => setCurrentSec(event.currentTarget.currentTime)}
                        onLoadedMetadata={handleVideoReady}
                        onCanPlay={handleVideoReady}
                        onError={handleVideoPlaybackError}
                        data-testid="video-player"
                      />
                      <Typography variant="caption" color="text.secondary" display="block" mt={1}>
                        Click any point on the timeline or a segment card to seek this player.
                      </Typography>

                      <Divider sx={{ my: 2 }} />

                      <Stack spacing={1.5}>
                        <Stack direction="row" flexWrap="wrap" gap={1}>
                          <Chip label={`Sessions ${qualitySummary?.sessions_count ?? 0}`} />
                          <Chip label={`Participants ${qualitySummary?.participants_count ?? 0}`} />
                          <Chip label={`Face OK ${((qualitySummary?.face_ok_rate ?? 0) * 100).toFixed(1)}%`} />
                          <Chip label={`Quality ${qualitySummary?.quality_badge ?? 'n/a'}`} color={qualitySummary?.quality_badge === 'high' ? 'success' : qualitySummary?.quality_badge === 'medium' ? 'warning' : 'default'} data-testid="quality-badge" />
                          <Chip label={`Usable ${(qualitySummary?.usable_seconds ?? 0).toFixed(1)}s`} data-testid="usable-seconds-chip" />
                          <Chip label={`Tracking ${(((qualitySummary?.mean_tracking_confidence ?? 0) * 100)).toFixed(1)}%`} />
                          <Chip label={`Trace ${formatTraceSource(qualitySummary?.trace_source)}`} color={qualitySummary?.trace_source === 'provided' ? 'success' : qualitySummary?.trace_source === 'synthetic_fallback' || qualitySummary?.trace_source === 'mixed' ? 'warning' : 'default'} data-testid="trace-source-badge" />
                        </Stack>

                        <Stack direction="row" flexWrap="wrap" gap={1} data-testid="playback-telemetry-card">
                          {(['pause', 'seek', 'abandonment'] as Array<TelemetryOverlayMarker['kind']>).map((kind) => (
                            <Chip key={kind} label={`${TELEMETRY_KIND_LABEL[kind]} ${telemetryCountByKind[kind]}`} data-testid={`telemetry-count-${kind}`} />
                          ))}
                        </Stack>

                        {abandonmentPoint ? (
                          <Alert severity="warning" data-testid="abandonment-point-card">
                            Abandonment at {(abandonmentPoint.video_time_ms / 1000).toFixed(1)}s{aggregateApplied ? ' (aggregate)' : ''}
                          </Alert>
                        ) : (
                          <Alert severity="success" data-testid="abandonment-point-empty">No abandonment events.</Alert>
                        )}

                        {qualityWarning ? (
                          <Alert severity="warning" data-testid="quality-warning">{qualityWarning}</Alert>
                        ) : (
                          <Alert severity="success" data-testid="quality-ok">Tracking confidence stable.</Alert>
                        )}

                        {predictionLoading ? <Alert severity="info" data-testid="prediction-overlay-loading">Generating prediction overlay…</Alert> : null}
                        {videoPlaybackError ? (
                          <Alert severity="error" data-testid="video-playback-error">{videoPlaybackError}</Alert>
                        ) : null}
                        {!videoPlaybackError && readout?.source_url_reachable === false ? (
                          <Alert severity="warning" data-testid="source-url-unreachable">
                            Video source URL is unreachable. The player may not load. Scores and traces are still valid.
                          </Alert>
                        ) : null}
                        {readout?.has_sufficient_watch_data === false ? (
                          <Alert severity="info" data-testid="insufficient-watch-data">
                            This session was abandoned before enough video was watched. Scores may not be meaningful.
                          </Alert>
                        ) : null}
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid size={{ xs: 12, lg: 7 }}>
                  <Card>
                    <CardContent>
                      <Accordion disableGutters expanded={traceLayersExpanded} onChange={(_event, expanded) => setTraceLayersExpanded(expanded)} sx={{ ...ACCORDION_BASE_SX, mb: 1.5 }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />} data-testid="trace-layers-summary">
                          <Stack direction="row" spacing={1} alignItems="center" width="100%" pr={1}>
                            <Typography variant="subtitle2" fontWeight={700}>Trace Layers</Typography>
                            <Chip size="small" label={traceLayerSummaryLabel} />
                            <Chip size="small" label={auSummaryLabel} />
                          </Stack>
                        </AccordionSummary>
                        <AccordionDetails sx={{ pt: 0, pb: 2.5 }}>
                          <Grid container spacing={2}>
                            <Grid size={{ xs: 12, lg: 6 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
                                <Typography variant="subtitle2" fontWeight={700}>Signals</Typography>
                                <Stack direction="row" spacing={1}>
                                  <Button size="small" variant="text" onClick={() => setLayerVisibility(DEFAULT_TRACE_LAYER_VISIBILITY)}>Core</Button>
                                  <Button size="small" variant="text" onClick={() => setAllTraceLayers(true)}>All</Button>
                                  <Button size="small" variant="text" onClick={() => setAllTraceLayers(false)}>None</Button>
                                </Stack>
                              </Stack>
                              <FormGroup sx={{ mt: 0.75 }}>
                                {TRACE_LAYER_OPTIONS.map((layer) => (
                                  <FormControlLabel key={layer.key} control={<Checkbox size="small" checked={layerVisibility[layer.key]} onChange={() => toggleLayer(layer.key)} data-testid={layer.testId} />} label={<TermTooltip term={layer.definitionKey}>{layer.label}</TermTooltip>} sx={{ my: 0.1 }} />
                                ))}
                              </FormGroup>
                            </Grid>
                            <Grid size={{ xs: 12, lg: 6 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
                                <Typography variant="subtitle2" fontWeight={700}>AU Channels</Typography>
                                <Stack direction="row" spacing={1}>
                                  <Button size="small" variant="text" onClick={() => setSelectedAuNames(availableAuNames.slice(0, 3))} disabled={availableAuNames.length === 0}>Top 3</Button>
                                  <Button size="small" variant="text" onClick={() => setSelectedAuNames(availableAuNames)} disabled={availableAuNames.length === 0}>All</Button>
                                  <Button size="small" variant="text" onClick={() => setSelectedAuNames([])} disabled={selectedAuNames.length === 0}>None</Button>
                                </Stack>
                              </Stack>
                              {availableAuNames.length === 0 ? (
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>AU channels appear after readout loads.</Typography>
                              ) : (
                                <FormGroup sx={{ mt: 0.75, maxHeight: 260, overflowY: 'auto', pr: 0.5 }}>
                                  {availableAuNames.map((auName) => (
                                    <FormControlLabel key={auName} control={<Checkbox size="small" checked={selectedAuNames.includes(auName)} onChange={() => toggleAu(auName)} data-testid={`toggle-au-${auName}`} />} label={auName} sx={{ my: 0.1 }} />
                                  ))}
                                </FormGroup>
                              )}
                            </Grid>
                          </Grid>
                        </AccordionDetails>
                      </Accordion>

                      {readout.neuro_scores ? (
                        <Card variant="outlined" sx={{ mb: 1.5 }} data-testid="neuro-snapshot-card">
                          <CardContent sx={{ py: 1.5 }}>
                            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} spacing={0.5} mb={1}>
                              <Typography variant="subtitle2" fontWeight={700}>Neuro Score Snapshot</Typography>
                              <Button size="small" variant="text" onClick={() => navigate(timelineReportPath)} data-testid="neuro-snapshot-open-timeline">Open Timeline Report</Button>
                            </Stack>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                              <Chip size="small" label={`Arrest ${formatIndexScore(readout.neuro_scores.scores.arrest_score.scalar_value)}`} data-testid="neuro-snapshot-arrest-chip" />
                              <Chip size="small" label={`Synchrony ${formatIndexScore(readout.neuro_scores.scores.attentional_synchrony_index.scalar_value)}`} data-testid="neuro-snapshot-synchrony-chip" />
                              <Chip size="small" label={`Narrative ${formatIndexScore(readout.neuro_scores.scores.narrative_control_score.scalar_value)}`} data-testid="neuro-snapshot-narrative-chip" />
                              <Chip size="small" label={`Blink Transport ${formatIndexScore(readout.neuro_scores.scores.blink_transport_score.scalar_value)}`} data-testid="neuro-snapshot-blink-chip" />
                              <Chip size="small" label={`Reward Anticipation ${formatIndexScore(readout.neuro_scores.scores.reward_anticipation_index.scalar_value)}`} data-testid="neuro-snapshot-reward-chip" />
                              <Chip size="small" label={`CTA Reception ${formatIndexScore(readout.neuro_scores.scores.cta_reception_score.scalar_value)}`} data-testid="neuro-snapshot-cta-chip" />
                              <Chip size="small" label={`Synthetic Lift ${formatIndexScore(readout.neuro_scores.scores.synthetic_lift_prior.scalar_value)}`} data-testid="neuro-snapshot-lift-chip" />
                            </Stack>
                          </CardContent>
                        </Card>
                      ) : (
                        <Alert severity="warning" sx={{ mb: 1.5 }} data-testid="neuro-snapshot-missing-alert">
                          Neuro taxonomy scores not returned. Verify <code>NEURO_SCORE_TAXONOMY_ENABLED</code>.
                        </Alert>
                      )}

                      {aggregateApplied ? (
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }} data-testid="ci-band-note">
                          Shaded bands show 95% confidence intervals for aggregate traces.
                        </Typography>
                      ) : null}

                      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 0.5 }}>
                        <FormControlLabel
                          control={<Switch size="small" checked={showPredictedOverlay} onChange={(e) => setShowPredictedOverlay(e.target.checked)} />}
                          label={<Typography variant="caption" color="text.secondary">Predicted overlay</Typography>}
                          labelPlacement="start"
                        />
                      </Box>
                      <SummaryChart
                        points={timelinePoints}
                        scenes={chartScenes}
                        cuts={chartCuts}
                        ctaMarkers={chartCtaMarkers}
                        annotationOverlays={annotationOverlays}
                        telemetryOverlays={telemetryOverlays}
                        isAggregateView={aggregateApplied}
                        availableAuNames={availableAuNames}
                        selectedAuNames={selectedAuNames}
                        layerVisibility={layerVisibility}
                        lowConfidenceWindows={lowConfidenceWindows}
                        showPredictedOverlay={showPredictedOverlay}
                        cursorSec={currentSec}
                        onSeek={handleSeek}
                      />

                      <Accordion disableGutters sx={{ ...ACCORDION_BASE_SX, mt: 1.5 }}>
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Typography variant="subtitle2" fontWeight={700}>Legend / How to read</Typography>
                        </AccordionSummary>
                        <AccordionDetails sx={{ pt: 0 }}>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
                            Lines are passive proxies aligned to <code>video_time_ms</code>; hover for exact values and click anywhere to seek.
                          </Typography>
                          <Grid container spacing={1.25}>
                            <Grid size={{ xs: 12, md: 6 }}>
                              <Typography variant="caption" sx={{ fontWeight: 700 }}>Trace lines</Typography>
                              <Stack spacing={0.5} mt={0.5}>
                                {TRACE_LEGEND_ITEMS.map((item) => (
                                  <Stack key={item.label} direction="row" spacing={1} alignItems="center">
                                    <Box sx={{ width: 18, borderTop: `3px ${item.dashed ? 'dashed' : 'solid'} ${item.color}`, flexShrink: 0 }} />
                                    <Typography variant="body2"><strong>{item.label}:</strong> {item.description}</Typography>
                                  </Stack>
                                ))}
                              </Stack>
                            </Grid>
                            <Grid size={{ xs: 12, md: 6 }}>
                              <Typography variant="caption" sx={{ fontWeight: 700 }}>Overlays</Typography>
                              <Stack spacing={0.5} mt={0.5}>
                                {OVERLAY_LEGEND_ITEMS.map((item) => (
                                  <Stack key={item.label} direction="row" spacing={1} alignItems="center">
                                    <Box sx={{ width: 18, borderTop: `3px ${item.dashed ? 'dashed' : 'solid'} ${item.color}`, flexShrink: 0 }} />
                                    <Typography variant="body2"><strong>{item.label}:</strong> {item.description}</Typography>
                                  </Stack>
                                ))}
                              </Stack>
                            </Grid>
                          </Grid>
                          <Alert severity="info" sx={{ mt: 1.25 }}>
                            Gaze-related signals are coarse webcam proxies, not precise eye tracking.
                          </Alert>
                        </AccordionDetails>
                      </Accordion>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Box>

            {/* ══════ SECTION 2 — Outcomes ══════ */}
            <Box>
              <SectionLabel>02 — Outcomes</SectionLabel>
              <Stack spacing={2}>
                <ProductRollupPanel productRollups={readout.product_rollups} />
                <NeuroScorecards neuroScores={readout.neuro_scores} legacyScoreAdapters={readout.legacy_score_adapters ?? []} onSeek={handleSeek} />
              </Stack>
            </Box>

            {/* ══════ SECTION 3 — Scene Diagnostics ══════ */}
            <Box>
              <SectionLabel>03 — Scene Diagnostics</SectionLabel>
              <Grid container spacing={2}>
                {DIAGNOSTIC_CARD_ORDER.map((cardType) => {
                  const card = diagnosticsByType.get(cardType);
                  const meta = DIAGNOSTIC_CARD_META[cardType];
                  const sceneNumber = card?.scene_index !== null && card?.scene_index !== undefined ? card.scene_index + 1 : null;
                  return (
                    <Grid key={cardType} size={{ xs: 12, md: 6, lg: 4 }}>
                      <Card data-testid={`diagnostic-card-${cardType}`}>
                        <CardContent>
                          <Stack spacing={1.25}>
                            <Typography variant="h6" fontWeight={700}>{meta.title}</Typography>
                            <Typography variant="body2" color="text.secondary">{meta.subtitle}</Typography>
                            {!card ? (
                              <Alert severity="info" sx={{ mt: 1 }}>No diagnostic data for this view.</Alert>
                            ) : (
                              <>
                                <Stack direction="row" spacing={1.5} alignItems="center">
                                  {card.scene_thumbnail_url ? (
                                    <Box component="img" src={card.scene_thumbnail_url} alt={card.scene_label ?? `${meta.title} scene`} sx={{ width: 76, height: 48, objectFit: 'cover', borderRadius: 1 }} />
                                  ) : (
                                    <Avatar variant="rounded" sx={{ width: 76, height: 48, bgcolor: 'primary.main' }}>
                                      {sceneNumber ? `S${sceneNumber}` : 'N/A'}
                                    </Avatar>
                                  )}
                                  <Stack spacing={0.25}>
                                    <Typography variant="body2" fontWeight={600}>
                                      {card.scene_label ?? (sceneNumber ? `Scene ${sceneNumber}` : 'Unaligned segment')}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {(card.start_video_time_ms / 1000).toFixed(1)}s – {(card.end_video_time_ms / 1000).toFixed(1)}s
                                    </Typography>
                                  </Stack>
                                </Stack>
                                <Typography variant="body2">
                                  <strong>{card.primary_metric}</strong>: {card.primary_metric_value.toFixed(2)}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">{card.why_flagged}</Typography>
                                <Stack direction="row" flexWrap="wrap" gap={0.5}>
                                  <Chip size="small" label={card.confidence !== null && card.confidence !== undefined ? `confidence ${(card.confidence * 100).toFixed(0)}%` : 'confidence n/a'} color={card.confidence !== null && card.confidence !== undefined && card.confidence < 0.5 ? 'warning' : 'default'} />
                                  {card.reason_codes.slice(0, 3).map((reason) => (
                                    <Chip size="small" key={`${cardType}-${reason}`} label={reason} variant="outlined" />
                                  ))}
                                </Stack>
                                <Button size="small" variant="outlined" onClick={() => handleSeek(card.start_video_time_ms / 1000)} data-testid={`diagnostic-jump-${cardType}`}>
                                  Jump To Scene
                                </Button>
                              </>
                            )}
                          </Stack>
                        </CardContent>
                      </Card>
                    </Grid>
                  );
                })}
                <Grid size={{ xs: 12, md: 6, lg: 4 }}>
                  <SegmentPanel title="Golden Scenes" subtitle="Strongest engagement/reward windows." metricLabel="score" segments={readout.segments.golden_scenes} onSeek={handleSeek} testId="golden-scenes-card" definitionKey="golden_scene" />
                </Grid>
                <Grid size={{ xs: 12, md: 6, lg: 4 }}>
                  <SegmentPanel title="Dead Zones" subtitle="Sustained attention drops." metricLabel="drop" segments={readout.segments.dead_zones} onSeek={handleSeek} testId="dead-zones-card" definitionKey="dead_zones" />
                </Grid>
                <Grid size={{ xs: 12, md: 6, lg: 4 }}>
                  <SegmentPanel title="Attention Gains" subtitle="Meaningful sustained rises in attention." metricLabel="gain" segments={readout.segments.attention_gain_segments} onSeek={handleSeek} testId="attention-gains-card" definitionKey="attention_gain_segments" />
                </Grid>
                <Grid size={{ xs: 12, md: 6, lg: 6 }}>
                  <SegmentPanel title="Attention Losses" subtitle="Meaningful sustained declines in attention." metricLabel="loss" segments={readout.segments.attention_loss_segments} onSeek={handleSeek} testId="attention-losses-card" definitionKey="attention_loss_segments" />
                </Grid>
                <Grid size={{ xs: 12, md: 6, lg: 6 }}>
                  <SegmentPanel title="Confusion / Friction" subtitle="Likely confusion from blink/AU and velocity patterns." metricLabel="friction" segments={readout.segments.confusion_segments} onSeek={handleSeek} testId="confusion-card" definitionKey="confusion_segments" />
                </Grid>
              </Grid>
            </Box>

            {/* ══════ SECTION 4 — Signal Diagnostics (aggregate only) ══════ */}
            {aggregateApplied && aggregateMetrics ? (
              <SignalDiagnosticsSection aggregateMetrics={aggregateMetrics} onSeek={handleSeek} />
            ) : null}

            {/* ══════ SECTION 5 — Labels & Annotations ══════ */}
            <Box>
              <SectionLabel>{aggregateApplied ? '05' : '04'} — Labels & Annotations</SectionLabel>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, lg: 8 }}>
                  <Card data-testid="annotations-card">
                    <CardContent>
                      <Typography variant="h6" fontWeight={700} gutterBottom>Explicit Label Overlays</Typography>
                      <Typography variant="body2" color="text.secondary" gutterBottom>Post-view timeline labels overlaid on the trace chart.</Typography>
                      <Stack direction="row" flexWrap="wrap" gap={1} mt={1} mb={1.5}>
                        {(['engaging_moment', 'confusing_moment', 'stop_watching_moment', 'cta_landed_moment'] as const).map((markerType) => (
                          <Chip key={markerType} label={`${MARKER_DISPLAY_LABEL[markerType]} ${markerCountByType(markerType)}`} data-testid={`marker-count-${markerType}`} />
                        ))}
                        <Chip label={`Total ${annotationSummary?.total_annotations ?? 0}`} variant="outlined" data-testid="marker-count-total" />
                      </Stack>
                      {aggregateApplied ? (
                        <Alert severity="info" sx={{ mb: 1.5 }} data-testid="marker-density-note">Marker density values normalized per selected session.</Alert>
                      ) : null}
                      <Divider sx={{ mb: 1.5 }} />
                      {readout.labels.annotations.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">No post-view annotations for this selection.</Typography>
                      ) : (
                        <List dense>
                          {readout.labels.annotations.map((annotation) => (
                            <ListItem key={annotation.id} secondaryAction={<Button variant="text" size="small" onClick={() => handleSeek(annotation.video_time_ms / 1000)}>Seek</Button>}>
                              <ListItemText primary={`${annotation.marker_type} @ ${(annotation.video_time_ms / 1000).toFixed(1)}s`} secondary={[annotation.note || 'No note', annotation.scene_id ? `scene ${annotation.scene_id}` : null, annotation.cut_id ? `cut ${annotation.cut_id}` : null, annotation.cta_id ? `cta ${annotation.cta_id}` : null].filter(Boolean).join(' • ')} />
                            </ListItem>
                          ))}
                        </List>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, lg: 4 }}>
                  <Card data-testid="labels-survey-summary-card">
                    <CardContent>
                      <Typography variant="h6" fontWeight={700} gutterBottom>Label + Survey Summary</Typography>
                      <Typography variant="body2" color="text.secondary" gutterBottom>Explicit labels and survey outcomes for this selection.</Typography>
                      <Divider sx={{ my: 1.5 }} />
                      <Typography variant="subtitle2" fontWeight={700}>Top engaging timestamps</Typography>
                      {renderTopTimestampList(annotationSummary?.top_engaging_timestamps ?? [], 'No engaging labels yet.', 'top-engaging')}
                      <Typography variant="subtitle2" fontWeight={700} mt={1}>Top confusing timestamps</Typography>
                      {renderTopTimestampList(annotationSummary?.top_confusing_timestamps ?? [], 'No confusing labels yet.', 'top-confusing')}
                      <Divider sx={{ my: 1.5 }} />
                      <Stack spacing={0.75} data-testid="survey-summary-block">
                        <Typography variant="subtitle2" fontWeight={700}>Survey summary</Typography>
                        <Typography variant="body2">Overall interest: {formatSurveyScore(surveySummary?.overall_interest_mean)}</Typography>
                        <Typography variant="body2">Comprehension / recall: {formatSurveyScore(surveySummary?.recall_comprehension_mean)}</Typography>
                        <Typography variant="body2">Keep watching / take action: {formatSurveyScore(surveySummary?.desire_to_continue_or_take_action_mean)}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          Responses: {surveySummary?.responses_count ?? 0} • Comments: {surveySummary?.comment_count ?? 0}
                        </Typography>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Box>

            {/* ══════ SECTION 6 — Reliability Rationale ══════ */}
            <Box>
              <SectionLabel>{aggregateApplied ? '06' : '05'} — Reliability Rationale</SectionLabel>
              {reliability ? (
                <Card variant="outlined" data-testid="readout-reliability-rationale-card">
                  <CardContent sx={{ py: 1.5 }}>
                    <Stack spacing={1}>
                      <Alert severity={reliabilityAlertSeverity} data-testid="readout-reliability-summary">
                        {reliabilitySummary}
                      </Alert>
                      <Stack direction="row" flexWrap="wrap" gap={0.75} data-testid="readout-reliability-components">
                        {reliabilityComponentBreakdown.map((component) => (
                          <Chip
                            key={component.key}
                            size="small"
                            label={`${component.label} ${component.score.toFixed(1)} (w=${component.weight})`}
                            variant="outlined"
                            data-testid={`readout-reliability-component-${component.key}`}
                          />
                        ))}
                      </Stack>
                      {reliabilitySupportIssues.length > 0 ? (
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                            Support for score:
                          </Typography>
                          <List dense sx={{ py: 0 }}>
                            {reliabilitySupportIssues.map((issue, index) => (
                              <ListItem key={`${issue}-${index}`} sx={{ py: 0.25, px: 0 }}>
                                <ListItemText primaryTypographyProps={{ variant: 'body2' }} primary={issue} />
                              </ListItem>
                            ))}
                          </List>
                        </Box>
                      ) : null}
                    </Stack>
                  </CardContent>
                </Card>
              ) : (
                <Alert severity="info" data-testid="readout-reliability-missing">
                  Reliability score is unavailable for this readout.
                </Alert>
              )}
            </Box>

            <Alert
              severity="info"
              data-testid="legacy-view-callout"
              action={<Button size="small" color="inherit" onClick={() => navigate(timelineReportPath)}>Open Timeline Report</Button>}
            >
              This is the legacy deep-dive surface. The full scene-by-scene score stack is available in Timeline Report.
            </Alert>
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
