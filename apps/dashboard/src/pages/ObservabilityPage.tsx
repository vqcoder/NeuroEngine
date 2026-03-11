import { useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Typography
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useNavigate } from 'react-router-dom';
import {
  fetchCaptureArchiveObservabilityStatus,
  fetchFrontendDiagnosticEvents,
  fetchFrontendDiagnosticsSummary,
  fetchNeuroObservabilityStatus,
  fetchPredictJobsObservabilityStatus
} from '../api';
import type {
  CaptureArchiveObservabilityStatus,
  FrontendDiagnosticEvent,
  FrontendDiagnosticSummary,
  NeuroObservabilityStatus,
  PredictJobsObservabilityStatus
} from '../types';

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value < 0) {
    return 'n/a';
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function statusChipColor(
  status: string
): 'default' | 'success' | 'warning' | 'error' | 'info' {
  if (status === 'ok') {
    return 'success';
  }
  if (status === 'alert') {
    return 'error';
  }
  if (status === 'disabled') {
    return 'warning';
  }
  if (status === 'no_history_config' || status === 'no_data') {
    return 'info';
  }
  return 'default';
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return 'n/a';
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString();
}

const EXPLANATION_SECTIONS = [
  {
    key: 'drift_alerts',
    title: 'Drift Alerts',
    body: 'Drift compares current score outputs against prior model snapshots. Alerts mean score deltas crossed your configured threshold.'
  },
  {
    key: 'missing_signal',
    title: 'Missing-Signal Rate',
    body: 'This is the share of scores that are unavailable or insufficient_data. Higher values usually mean weaker input coverage or quality.'
  },
  {
    key: 'fallback_rate',
    title: 'Fallback-Path Rate',
    body: 'This tracks how often modules used fallback estimation instead of a primary pathway. More fallback usage usually lowers confidence.'
  },
  {
    key: 'confidence_mean',
    title: 'Confidence Mean',
    body: 'Average confidence across available scores in recent observability snapshots. This does not guarantee causal truth, it reflects signal quality.'
  }
] as const;

export default function ObservabilityPage() {
  const navigate = useNavigate();
  const [payload, setPayload] = useState<NeuroObservabilityStatus | null>(null);
  const [capturePayload, setCapturePayload] = useState<CaptureArchiveObservabilityStatus | null>(null);
  const [frontendSummary, setFrontendSummary] = useState<FrontendDiagnosticSummary | null>(null);
  const [frontendEvents, setFrontendEvents] = useState<FrontendDiagnosticEvent[]>([]);
  const [predictJobsPayload, setPredictJobsPayload] = useState<PredictJobsObservabilityStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const [neuroStatus, captureStatus] = await Promise.all([
        fetchNeuroObservabilityStatus(),
        fetchCaptureArchiveObservabilityStatus()
      ]);
      setPayload(neuroStatus);
      setCapturePayload(captureStatus);
      try {
        const [frontendSummaryPayload, frontendEventsPayload] = await Promise.all([
          fetchFrontendDiagnosticsSummary(24, 8),
          fetchFrontendDiagnosticEvents({ limit: 12 })
        ]);
        setFrontendSummary(frontendSummaryPayload);
        setFrontendEvents(frontendEventsPayload.items ?? []);
      } catch {
        setFrontendSummary(null);
        setFrontendEvents([]);
      }
      try {
        setPredictJobsPayload(await fetchPredictJobsObservabilityStatus());
      } catch {
        setPredictJobsPayload(null);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load observability status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  const warningList = useMemo(() => payload?.warnings ?? [], [payload]);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1100, mx: 'auto' }}>
      <Stack spacing={2.5}>
        <Card data-testid="observability-header-card">
          <CardContent>
            <Stack spacing={1.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={1}>
                <Box>
                  <Typography variant="h4" fontWeight={700} data-testid="observability-title">
                    Neuro Score Observability
                  </Typography>
                  <Typography color="text.secondary">
                    Runtime checks for drift, missing signals, fallback usage, and confidence coverage.
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    This panel reports model telemetry health. It does not make biochemical claims.
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1} alignItems="flex-start">
                  <Button
                    variant="outlined"
                    startIcon={<ArrowBackIcon />}
                    onClick={() => navigate('/')}
                    data-testid="observability-back-home"
                  >
                    Home
                  </Button>
                  <Button
                    variant="outlined"
                    startIcon={<RefreshIcon />}
                    onClick={loadStatus}
                    disabled={loading}
                    data-testid="observability-refresh"
                  >
                    Refresh
                  </Button>
                </Stack>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        {loading ? (
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" data-testid="observability-loading">
                <CircularProgress size={20} />
                <Typography color="text.secondary">Loading observability status…</Typography>
              </Stack>
            </CardContent>
          </Card>
        ) : null}

        {error ? (
          <Alert severity="error" data-testid="observability-error">
            {error}
          </Alert>
        ) : null}

        {!loading && !error && payload ? (
          <>
            <Card data-testid="observability-summary-card">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6" fontWeight={700}>
                    Summary
                  </Typography>
                  <Stack direction="row" flexWrap="wrap" gap={1}>
                    <Chip
                      label={`Status ${payload.status}`}
                      color={statusChipColor(payload.status)}
                      data-testid="observability-status-chip"
                    />
                    <Chip label={`Enabled ${payload.enabled ? 'yes' : 'no'}`} />
                    <Chip label={`History ${payload.history_enabled ? 'on' : 'off'}`} />
                    <Chip label={`Entries ${payload.history_entry_count}`} />
                    <Chip label={`Recent alerts ${payload.recent_drift_alert_count}`} />
                    <Chip label={`Missing signal ${formatPercent(payload.mean_missing_signal_rate)}`} />
                    <Chip label={`Fallback ${formatPercent(payload.mean_fallback_rate)}`} />
                    <Chip label={`Confidence ${formatPercent(payload.mean_confidence)}`} />
                  </Stack>

                  {warningList.length > 0 ? (
                    <Alert severity="warning" data-testid="observability-warning">
                      {warningList.join(' | ')}
                    </Alert>
                  ) : (
                    <Alert severity="success" data-testid="observability-no-warning">
                      No active observability warnings in the current window.
                    </Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="capture-observability-card">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6" fontWeight={700}>
                    Capture Archive Ops
                  </Typography>
                  {capturePayload ? (
                    <>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip
                          label={`Status ${capturePayload.status}`}
                          color={statusChipColor(capturePayload.status)}
                        />
                        <Chip label={`Enabled ${capturePayload.enabled ? 'yes' : 'no'}`} />
                        <Chip label={`Purge ${capturePayload.purge_enabled ? 'on' : 'off'}`} />
                        <Chip label={`Encryption ${capturePayload.encryption_mode}`} />
                        <Chip label={`Retention ${capturePayload.retention_days}d`} />
                        <Chip label={`Batch ${capturePayload.purge_batch_size}`} />
                      </Stack>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`Events ${capturePayload.ingestion_event_count}`} />
                        <Chip label={`Success ${capturePayload.success_count}`} color="success" />
                        <Chip label={`Failure ${capturePayload.failure_count}`} color="error" />
                        <Chip label={`Failure rate ${formatPercent(capturePayload.failure_rate)}`} />
                        <Chip
                          label={`Recent ${capturePayload.recent_window_hours}h failure ${formatPercent(
                            capturePayload.recent_failure_rate
                          )}`}
                        />
                      </Stack>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`Archives ${capturePayload.total_archives}`} />
                        <Chip label={`Frames ${capturePayload.total_frames}`} />
                        <Chip label={`Pointers ${capturePayload.total_frame_pointers}`} />
                        <Chip label={`Raw ${formatBytes(capturePayload.total_uncompressed_bytes)}`} />
                        <Chip
                          label={`Stored ${formatBytes(capturePayload.total_compressed_bytes)}`}
                        />
                      </Stack>
                      {capturePayload.top_failure_codes.length > 0 ? (
                        <Alert severity="warning" data-testid="capture-observability-failures">
                          Top failure codes:{' '}
                          {capturePayload.top_failure_codes
                            .map((item) => `${item.error_code} (${item.count})`)
                            .join(', ')}
                        </Alert>
                      ) : (
                        <Alert severity="success" data-testid="capture-observability-failures-clear">
                          No capture ingest failures recorded.
                        </Alert>
                      )}
                      {capturePayload.warnings.length > 0 ? (
                        <Alert severity="warning">{capturePayload.warnings.join(' | ')}</Alert>
                      ) : null}
                    </>
                  ) : (
                    <Alert severity="info">Capture archive observability is not available.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="frontend-diagnostics-card">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6" fontWeight={700}>
                    Frontend Diagnostics
                  </Typography>
                  {frontendSummary ? (
                    <>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip
                          label={`Status ${frontendSummary.status}`}
                          color={statusChipColor(frontendSummary.status)}
                        />
                        <Chip label={`Window ${frontendSummary.window_hours}h`} />
                        <Chip label={`Events ${frontendSummary.total_events}`} />
                        <Chip label={`Errors ${frontendSummary.error_count}`} color="error" />
                        <Chip label={`Warnings ${frontendSummary.warning_count}`} color="warning" />
                        <Chip label={`Info ${frontendSummary.info_count}`} color="info" />
                        <Chip label={`Last ${formatTimestamp(frontendSummary.last_event_at)}`} />
                      </Stack>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        {(frontendSummary.active_pages ?? []).map((pageName) => (
                          <Chip
                            key={`frontend-page-${pageName}`}
                            label={`Page ${pageName}`}
                            variant="outlined"
                          />
                        ))}
                      </Stack>
                      {frontendSummary.top_errors.length > 0 ? (
                        <Alert severity="warning" data-testid="frontend-diagnostics-top-errors">
                          Top frontend failures:{' '}
                          {frontendSummary.top_errors
                            .map((item) => `${item.event_type}/${item.error_code} (${item.count})`)
                            .join(', ')}
                        </Alert>
                      ) : (
                        <Alert severity="success" data-testid="frontend-diagnostics-top-errors-clear">
                          No frontend failures recorded in the current window.
                        </Alert>
                      )}
                      {frontendSummary.warnings.length > 0 ? (
                        <Alert severity="warning">{frontendSummary.warnings.join(' | ')}</Alert>
                      ) : null}
                    </>
                  ) : (
                    <Alert severity="info">Frontend diagnostics summary is unavailable.</Alert>
                  )}
                  <Divider />
                  <Typography variant="subtitle2" fontWeight={600}>
                    Recent frontend events
                  </Typography>
                  {frontendEvents.length > 0 ? (
                    <Stack spacing={0.5}>
                      {frontendEvents.map((event) => (
                        <Typography
                          key={event.id}
                          variant="body2"
                          color="text.secondary"
                          data-testid={`frontend-diagnostic-event-${event.id}`}
                        >
                          [{formatTimestamp(event.created_at)}] {event.surface}/{event.page} •{' '}
                          {event.event_type}
                          {event.error_code ? ` (${event.error_code})` : ''}
                          {event.message ? ` — ${event.message}` : ''}
                        </Typography>
                      ))}
                    </Stack>
                  ) : (
                    <Alert severity="info" data-testid="frontend-diagnostics-empty">
                      No recent frontend diagnostics events.
                    </Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="observability-latest-card">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="h6" fontWeight={700}>
                    Latest Snapshot
                  </Typography>
                  {payload.latest_snapshot ? (
                    <>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`Recorded ${payload.latest_snapshot.recorded_at ?? 'n/a'}`} />
                        <Chip label={`Video ${payload.latest_snapshot.video_id ?? 'n/a'}`} />
                        <Chip label={`Variant ${payload.latest_snapshot.variant_id ?? 'n/a'}`} />
                        <Chip label={`Model ${payload.latest_snapshot.model_signature ?? 'n/a'}`} />
                        <Chip
                          label={`Drift ${payload.latest_snapshot.drift_status ?? 'n/a'}`}
                          color={statusChipColor(payload.latest_snapshot.drift_status ?? 'unknown')}
                        />
                      </Stack>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`Missing signal ${formatPercent(payload.latest_snapshot.missing_signal_rate)}`} />
                        <Chip label={`Fallback ${formatPercent(payload.latest_snapshot.fallback_rate)}`} />
                        <Chip label={`Confidence ${formatPercent(payload.latest_snapshot.confidence_mean)}`} />
                      </Stack>
                      {payload.latest_snapshot.metrics_exceeding_threshold.length > 0 ? (
                        <Alert severity="error" data-testid="observability-latest-drift-alert">
                          Threshold exceeded: {payload.latest_snapshot.metrics_exceeding_threshold.join(', ')}
                        </Alert>
                      ) : (
                        <Alert severity="info" data-testid="observability-latest-drift-clear">
                          No metrics exceeded the drift threshold in the latest snapshot.
                        </Alert>
                      )}
                    </>
                  ) : (
                    <Alert severity="info" data-testid="observability-latest-empty">
                      No observability history entries yet. Enable history path and generate readouts.
                    </Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="observability-config-card">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="h6" fontWeight={700}>
                    Runtime Config
                  </Typography>
                  <Stack direction="row" flexWrap="wrap" gap={1}>
                    <Chip label={`History max entries ${payload.history_max_entries}`} />
                    <Chip label={`Drift threshold ${payload.drift_alert_threshold.toFixed(2)}`} />
                    <Chip label={`Recent window ${payload.recent_window}`} />
                    <Chip label={`Recent snapshots ${payload.recent_snapshot_count}`} />
                    <Chip label={`Alert rate ${formatPercent(payload.recent_drift_alert_rate)}`} />
                  </Stack>
                  <Divider />
                  <Typography variant="body2" color="text.secondary">
                    Core env vars:
                    {' '}
                    <code>NEURO_OBSERVABILITY_ENABLED</code>,
                    {' '}
                    <code>NEURO_OBSERVABILITY_HISTORY_PATH</code>,
                    {' '}
                    <code>NEURO_OBSERVABILITY_HISTORY_MAX_ENTRIES</code>,
                    {' '}
                    <code>NEURO_OBSERVABILITY_DRIFT_ALERT_THRESHOLD</code>.
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Capture env vars:
                    {' '}
                    <code>WEBCAM_CAPTURE_ARCHIVE_ENABLED</code>,
                    {' '}
                    <code>WEBCAM_CAPTURE_ARCHIVE_RETENTION_DAYS</code>,
                    {' '}
                    <code>WEBCAM_CAPTURE_ARCHIVE_PURGE_BATCH_SIZE</code>,
                    {' '}
                    <code>WEBCAM_CAPTURE_ARCHIVE_ENCRYPTION_MODE</code>.
                  </Typography>
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="predict-jobs-observability-card">
              <CardContent>
                <Stack spacing={1.5}>
                  <Typography variant="h6" fontWeight={700}>
                    Predict Job Queue
                  </Typography>
                  {predictJobsPayload ? (
                    <>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`Active ${predictJobsPayload.active_jobs}`} color={predictJobsPayload.active_jobs > 0 ? 'info' : 'default'} />
                        <Chip label={`Queued total ${predictJobsPayload.queued_total}`} />
                        <Chip label={`Completed ${predictJobsPayload.completed_total}`} color={predictJobsPayload.completed_total > 0 ? 'success' : 'default'} />
                        <Chip label={`Failed ${predictJobsPayload.failed_total}`} color={predictJobsPayload.failed_total > 0 ? 'error' : 'default'} />
                      </Stack>
                      <Stack direction="row" flexWrap="wrap" gap={1}>
                        <Chip label={`GitHub upload attempts ${predictJobsPayload.github_upload_attempts}`} />
                        <Chip label={`Successes ${predictJobsPayload.github_upload_successes}`} color={predictJobsPayload.github_upload_successes > 0 ? 'success' : 'default'} />
                        <Chip label={`Failures ${predictJobsPayload.github_upload_failures}`} color={predictJobsPayload.github_upload_failures > 0 ? 'warning' : 'default'} />
                        <Chip label={`Upload success rate ${formatPercent(predictJobsPayload.github_upload_success_rate)}`} />
                      </Stack>
                      {predictJobsPayload.failed_total > 0 ? (
                        <Alert severity="warning">
                          {predictJobsPayload.failed_total} predict job{predictJobsPayload.failed_total !== 1 ? 's' : ''} failed this session.
                        </Alert>
                      ) : predictJobsPayload.queued_total > 0 ? (
                        <Alert severity="success">No predict job failures this session.</Alert>
                      ) : (
                        <Alert severity="info">No predict jobs run this session yet.</Alert>
                      )}
                    </>
                  ) : (
                    <Alert severity="info">Predict job stats unavailable.</Alert>
                  )}
                </Stack>
              </CardContent>
            </Card>

            <Card data-testid="observability-explain-card">
              <CardContent>
                <Stack spacing={1}>
                  <Typography variant="h6" fontWeight={700}>
                    Explain This Page
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Expand each definition for plain-English interpretation.
                  </Typography>
                  {EXPLANATION_SECTIONS.map((item) => (
                    <Accordion key={item.key} disableGutters>
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography fontWeight={600}>{item.title}</Typography>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Typography variant="body2" color="text.secondary">
                          {item.body}
                        </Typography>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
