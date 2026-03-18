// TODO(A27): 707 lines — extract TrackEvidenceSummary, TimelineControls
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  Grid,
  Stack,
  Switch,
  TextField,
  Typography
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { fetchVideoReadout, reportFrontendDiagnosticFireAndForget } from '../api';
import RetryAlert from '../components/RetryAlert';
import SummaryChart from '../components/SummaryChart';
import TimelineTrackLanes from '../components/TimelineTrackLanes';
import ProductRollupPanel from '../components/ProductRollupPanel';
import type {
  AnnotationOverlayMarker,
  PlaybackTelemetryEvent,
  ReadoutCut,
  ReadoutScene,
  TelemetryOverlayMarker,
  TraceLayerVisibility,
  VideoReadout
} from '../types';
import {
  buildTimelineKeyMoments,
  buildTimelineTracks,
  DEFAULT_TIMELINE_TRACK_VISIBILITY,
  type TimelineTrackKey,
  type TimelineTrackVisibility
} from '../utils/timelineReport';
import { mapReadoutToTimeline } from '../utils/readout';
import {
  asUuidOrUndefined,
  buildVideoSourceCandidates,
  DEFAULT_WINDOW_MS,
  isHttpUrl,
  SAMPLE_VIDEO_URL,
} from '../utils/videoDashboard';

const ABANDONMENT_EVENT_TYPES = new Set([
  'abandonment',
  'session_incomplete',
  'incomplete_session',
  'abandon'
]);

const toTelemetryOverlayKind = (
  eventType: string
): TelemetryOverlayMarker['kind'] | null => {
  const normalized = eventType.trim().toLowerCase();
  if (normalized === 'pause') {
    return 'pause';
  }
  if (normalized === 'seek' || normalized === 'seek_start' || normalized === 'seek_end' || normalized === 'rewind') {
    return 'seek';
  }
  if (ABANDONMENT_EVENT_TYPES.has(normalized)) {
    return 'abandonment';
  }
  if (normalized === 'audio_reaction') {
    return 'audio_reaction';
  }
  return null;
};

const TRACE_LAYER_TEMPLATE: TraceLayerVisibility = {
  attentionScore: true,
  attentionVelocity: false,
  blinkRate: false,
  blinkInhibition: true,
  rewardProxy: true,
  valenceProxy: false,
  arousalProxy: false,
  noveltyProxy: false,
  trackingConfidence: true
};

export default function VideoTimelineReportPage() {
  const navigate = useNavigate();
  const { videoId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [readout, setReadout] = useState<VideoReadout | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [videoSourceCandidates, setVideoSourceCandidates] = useState<string[]>([SAMPLE_VIDEO_URL]);
  const [activeVideoSourceIndex, setActiveVideoSourceIndex] = useState(0);
  const [videoPlaybackError, setVideoPlaybackError] = useState<string | null>(null);
  const videoSrc =
    videoSourceCandidates[Math.min(activeVideoSourceIndex, Math.max(0, videoSourceCandidates.length - 1))] ??
    SAMPLE_VIDEO_URL;

  const reportTimelineDiagnostic = ({
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
        : `/videos/${encodeURIComponent(videoId)}/timeline-report`;
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
        view: 'timeline_report',
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
  const [trackVisibility, setTrackVisibility] = useState<TimelineTrackVisibility>(
    DEFAULT_TIMELINE_TRACK_VISIBILITY
  );
  const [showPredictedOverlay, setShowPredictedOverlay] = useState(false);

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
      const returnedVideoId = (payload as Record<string, unknown>).video_id;
      if (returnedVideoId && returnedVideoId !== normalizedVideoId) {
        throw new Error(
          `Readout mismatch: requested "${normalizedVideoId}" but API returned "${returnedVideoId}". Refusing to display.`
        );
      }
      setReadout(payload as VideoReadout);
    } catch (loadError) {
      const message =
        loadError instanceof Error ? loadError.message : 'Failed to load timeline report';
      setError(message);
      reportTimelineDiagnostic({
        severity: 'error',
        eventType: 'timeline_report_fetch_failed',
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
    const sourceUrl = readout?.source_url?.trim() ?? '';
    setVideoSourceCandidates(buildVideoSourceCandidates(sourceUrl));
    setActiveVideoSourceIndex(0);
    setVideoPlaybackError(null);
  }, [readout]);

  const chartScenes = useMemo<ReadoutScene[]>(() => readout?.context.scenes ?? [], [readout]);
  const chartCuts = useMemo<ReadoutCut[]>(() => readout?.context.cuts ?? [], [readout]);
  const chartCtaMarkers = useMemo(() => readout?.context.cta_markers ?? [], [readout]);

  const annotationOverlays = useMemo<AnnotationOverlayMarker[]>(() => {
    if (!readout) {
      return [];
    }
    if (aggregateApplied) {
      return [...(readout.labels.annotation_summary?.marker_density ?? [])].sort(
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
  }, [aggregateApplied, readout]);

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

  const lowConfidenceWindows = useMemo(
    () =>
      (readout?.quality.low_confidence_windows ?? []).map((window) => ({
        startSec: window.start_video_time_ms / 1000,
        endSec: window.end_video_time_ms / 1000,
        qualityFlags: window.quality_flags ?? []
      })),
    [readout]
  );

  const timelinePoints = useMemo(() => {
    if (!readout) {
      return [];
    }
    return mapReadoutToTimeline(readout);
  }, [readout]);

  const timelineTracks = useMemo(() => {
    if (!readout) {
      return [];
    }
    return buildTimelineTracks(readout);
  }, [readout]);

  const keyMoments = useMemo(() => {
    if (!readout) {
      return [];
    }
    return buildTimelineKeyMoments(readout);
  }, [readout]);

  const trackCounts = useMemo(() => {
    return timelineTracks.reduce(
      (counts, track) => {
        counts[track.key] = track.windows.length;
        return counts;
      },
      {
        attention_arrest: 0,
        attentional_synchrony: 0,
        narrative_control: 0,
        blink_transport: 0,
        reward_anticipation: 0,
        boundary_encoding: 0,
        cta_reception: 0,
        au_friction: 0
      } as Record<TimelineTrackKey, number>
    );
  }, [timelineTracks]);

  const visibleTrackCount = useMemo(
    () => Object.values(trackVisibility).filter(Boolean).length,
    [trackVisibility]
  );

  const summaryChartLayerVisibility = useMemo<TraceLayerVisibility>(() => {
    return {
      ...TRACE_LAYER_TEMPLATE,
      attentionScore: trackVisibility.attention_arrest,
      blinkInhibition: trackVisibility.blink_transport,
      rewardProxy: trackVisibility.reward_anticipation
    };
  }, [trackVisibility]);

  const qualitySummary = readout?.quality.session_quality_summary;
  const aggregateMetrics = readout?.aggregate_metrics;
  const normalizeIndexToSignedSynchrony = (value: number | null | undefined): number | null => {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return null;
    }
    return Math.max(-1, Math.min(1, (value / 50) - 1));
  };
  const formatSynchronyValue = (value: number | null | undefined): string =>
    value === null || value === undefined ? 'n/a' : value.toFixed(3);
  const resolvedAttentionSynchrony =
    aggregateMetrics?.attention_synchrony ??
    normalizeIndexToSignedSynchrony(aggregateMetrics?.attentional_synchrony?.global_score);
  const resolvedGripControl = (() => {
    if (aggregateMetrics?.grip_control_score !== null && aggregateMetrics?.grip_control_score !== undefined) {
      return aggregateMetrics.grip_control_score;
    }
    if (resolvedAttentionSynchrony !== null && resolvedAttentionSynchrony !== undefined) {
      return resolvedAttentionSynchrony;
    }
    return normalizeIndexToSignedSynchrony(aggregateMetrics?.narrative_control?.global_score);
  })();

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

  const handleSeek = (seconds: number) => {
    if (!Number.isFinite(seconds)) {
      return;
    }
    const targetSeconds = Math.max(0, seconds);
    const video = videoRef.current;
    if (!video) {
      setCurrentSec(targetSeconds);
      return;
    }

    const hasFiniteDuration = Number.isFinite(video.duration) && video.duration > 0;
    const maxSeconds = hasFiniteDuration ? Math.max(0, video.duration - 0.01) : targetSeconds;
    const bounded = Math.min(targetSeconds, maxSeconds);
    try {
      video.currentTime = bounded;
      setCurrentSec(bounded);
    } catch {
      setCurrentSec(bounded);
    }
  };

  const handleVideoReady = () => {
    setVideoPlaybackError(null);
  };

  const handleVideoPlaybackError = () => {
    setActiveVideoSourceIndex((currentIndex) => {
      if (currentIndex + 1 < videoSourceCandidates.length) {
        reportTimelineDiagnostic({
          severity: 'warning',
          eventType: 'timeline_report_video_source_fallback',
          errorCode: 'candidate_failed',
          message: 'Timeline report player advanced to a fallback source candidate.',
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
      reportTimelineDiagnostic({
        severity: 'error',
        eventType: 'timeline_report_video_playback_failed',
        errorCode: 'all_candidates_failed',
        message,
        context: {
          playback_candidates: videoSourceCandidates
        }
      });
      return currentIndex;
    });
  };

  const toggleTrack = (trackKey: TimelineTrackKey) => {
    setTrackVisibility((current) => ({
      ...current,
      [trackKey]: !current[trackKey]
    }));
  };

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1500, mx: 'auto' }} data-testid="timeline-report-root">
      <Stack spacing={2}>
        <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1}>
          <Box>
            <Typography variant="h4" fontWeight={700} data-testid="timeline-report-title">
              Scene-by-Scene Timeline Report
            </Typography>
            <Typography color="text.secondary">Video ID: {normalizedVideoId || videoId}</Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip label={`Current: ${currentSec.toFixed(1)}s`} color="primary" data-testid="timeline-current-time-chip" />
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={() => navigate(`/videos/${encodeURIComponent(normalizedVideoId)}`)}
              data-testid="open-legacy-report-button"
            >
              Open Legacy Report
            </Button>
          </Stack>
        </Stack>

        <Card>
          <CardContent>
            <Stack
              direction={{ xs: 'column', md: 'row' }}
              spacing={2}
              alignItems={{ xs: 'flex-start', md: 'center' }}
            >
              <FormControlLabel
                control={
                  <Switch
                    checked={aggregateDraft}
                    onChange={(event) => setAggregateDraft(event.target.checked)}
                    data-testid="timeline-aggregate-switch"
                  />
                }
                label={aggregateDraft ? 'Aggregate View' : 'Single Session View'}
              />
              <TextField
                size="small"
                label="Session ID"
                value={sessionDraft}
                onChange={(event) => setSessionDraft(event.target.value)}
                disabled={aggregateDraft}
                inputProps={{ 'data-testid': 'timeline-session-id-filter' }}
              />
              <TextField
                size="small"
                label="Variant ID"
                value={variantDraft}
                onChange={(event) => setVariantDraft(event.target.value)}
                inputProps={{ 'data-testid': 'timeline-variant-id-filter' }}
              />
              <TextField
                size="small"
                label="Window (ms)"
                type="number"
                value={windowMsDraft}
                onChange={(event) => setWindowMsDraft(Number(event.target.value) || DEFAULT_WINDOW_MS)}
                inputProps={{ min: 100, max: 10000, step: 100, 'data-testid': 'timeline-window-ms-filter' }}
              />
              <Button variant="outlined" onClick={handleApplyFilters} data-testid="timeline-apply-filter-button">
                Apply
              </Button>
            </Stack>
          </CardContent>
        </Card>

        {loading ? (
          <Box sx={{ py: 6, textAlign: 'center' }}>
            <CircularProgress />
          </Box>
        ) : null}

        {error ? <RetryAlert message={error} onRetry={loadReadout} /> : null}

        {!loading && !error && readout ? (
          <>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, lg: 4 }}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" fontWeight={700} gutterBottom>
                      Video Player
                    </Typography>
                    <video
                      ref={videoRef}
                      src={videoSrc}
                      controls
                      width="100%"
                      onTimeUpdate={(event) => setCurrentSec(event.currentTarget.currentTime)}
                      onLoadedMetadata={handleVideoReady}
                      onCanPlay={handleVideoReady}
                      onError={handleVideoPlaybackError}
                      data-testid="timeline-video-player"
                    />
                    {videoPlaybackError ? (
                      <Alert severity="error" sx={{ mt: 1 }} data-testid="timeline-video-playback-error">
                        {videoPlaybackError}
                      </Alert>
                    ) : null}
                    <Typography variant="body2" color="text.secondary" mt={1}>
                      Click timeline windows to seek this player.
                    </Typography>
                    <Divider sx={{ my: 1.25 }} />
                    <Stack direction="row" flexWrap="wrap" gap={1}>
                      <Chip label={`Visible tracks ${visibleTrackCount}/8`} data-testid="timeline-visible-tracks-chip" />
                      <Chip
                        label={`Key moments ${keyMoments.length}`}
                        data-testid="timeline-key-moment-count-chip"
                      />
                      <Chip
                        label={`Low-confidence windows ${readout.quality.low_confidence_windows.length}`}
                        data-testid="timeline-quality-window-count-chip"
                      />
                    </Stack>
                    <Typography variant="caption" color="text.secondary" display="block" mt={1.25}>
                      This view surfaces diagnostic, claim-safe evidence windows. GeoX or holdout results remain the truth layer for measured lift.
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid size={{ xs: 12, lg: 8 }}>
                <Card>
                  <CardContent>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                      <Typography variant="h6" fontWeight={700}>
                        Primary Timeline Overlay
                      </Typography>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={showPredictedOverlay}
                            onChange={(e) => setShowPredictedOverlay(e.target.checked)}
                          />
                        }
                        label={<Typography variant="caption" color="text.secondary">Predicted overlay</Typography>}
                        labelPlacement="start"
                      />
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Full asset timeline with scene boundaries, CTA windows, telemetry markers, and selected score overlays.
                    </Typography>
                    <SummaryChart
                      points={timelinePoints}
                      scenes={chartScenes}
                      cuts={chartCuts}
                      ctaMarkers={chartCtaMarkers}
                      annotationOverlays={annotationOverlays}
                      telemetryOverlays={telemetryOverlays}
                      isAggregateView={aggregateApplied}
                      layerVisibility={summaryChartLayerVisibility}
                      lowConfidenceWindows={lowConfidenceWindows}
                      showPredictedOverlay={showPredictedOverlay}
                      cursorSec={currentSec}
                      onSeek={handleSeek}
                    />
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <TimelineTrackLanes
              durationMs={readout.duration_ms}
              scenes={chartScenes}
              cuts={chartCuts}
              tracks={timelineTracks}
              visibility={trackVisibility}
              onToggleTrack={toggleTrack}
              onSeek={handleSeek}
              keyMoments={keyMoments}
            />
            <ProductRollupPanel productRollups={readout.product_rollups} />

            <Card>
              <CardContent>
                <Typography variant="h6" fontWeight={700} gutterBottom>
                  Timeline Overlay Diagnostics
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1}>
                  <Chip
                    label={`Attention synchrony ${formatSynchronyValue(resolvedAttentionSynchrony)}`}
                    data-testid="timeline-attention-synchrony-chip"
                  />
                  <Chip
                    label={`Blink synchrony ${formatSynchronyValue(aggregateMetrics?.blink_synchrony)}`}
                    data-testid="timeline-blink-synchrony-chip"
                  />
                  <Chip
                    label={`Grip control ${formatSynchronyValue(resolvedGripControl)}`}
                    data-testid="timeline-grip-control-chip"
                  />
                  <Chip
                    label={`Quality badge ${qualitySummary?.quality_badge ?? 'n/a'}`}
                    data-testid="timeline-quality-badge-chip"
                  />
                </Stack>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                  Track Evidence Window Summary
                </Typography>
                <Grid container spacing={1.25}>
                  {timelineTracks.map((track) => (
                    <Grid key={track.key} size={{ xs: 12, md: 6, lg: 4 }}>
                      <Card variant="outlined" data-testid={`timeline-track-summary-${track.key}`}>
                        <CardContent>
                          <Typography variant="subtitle2" fontWeight={700} sx={{ color: track.color }}>
                            {track.label}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                            {track.description}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                            Evidence windows: {track.windows.length}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
