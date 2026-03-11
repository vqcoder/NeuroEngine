// TODO(A26): 859 lines — extract CatalogGrid, SessionsPanel, QuickAccessForm
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  TextField,
  Typography
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { fetchVideoCatalog, fetchAnalystSessions, deleteVideo } from '../api';
import RetryAlert from '../components/RetryAlert';
import type { VideoCatalogItem, VideoCatalogSession, AnalystSession, AnalystSessionsResponse } from '../types';

const DEFAULT_VIDEO_ID = import.meta.env.VITE_DEFAULT_VIDEO_ID ?? '';
const DEFAULT_REPORT_VIEW = (import.meta.env.VITE_DEFAULT_REPORT_VIEW ?? 'timeline').trim().toLowerCase();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type HomeInputResolution =
  | { type: 'video'; videoId: string }
  | { type: 'predictor'; videoUrl: string };

function resolveHomeInput(value: string): HomeInputResolution | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const pathMatch = trimmed.match(/\/videos\/([^/?#]+)/i);
  if (pathMatch?.[1]) {
    return { type: 'video', videoId: decodeURIComponent(pathMatch[1]) };
  }

  try {
    const parsed = new URL(trimmed);
    const segments = parsed.pathname.split('/').filter(Boolean);
    const videosIndex = segments.findIndex((segment) => segment.toLowerCase() === 'videos');
    if (videosIndex >= 0 && segments[videosIndex + 1]) {
      return { type: 'video', videoId: decodeURIComponent(segments[videosIndex + 1]) };
    }

    const queryVideoId = (
      parsed.searchParams.get('video_id') ?? parsed.searchParams.get('videoId')
    )?.trim();
    if (queryVideoId) {
      return { type: 'video', videoId: queryVideoId };
    }

    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return { type: 'predictor', videoUrl: parsed.toString() };
    }
  } catch {
    return { type: 'video', videoId: trimmed };
  }

  return { type: 'video', videoId: trimmed };
}

function buildVideoReportPath(videoId: string, options?: { forceLegacy?: boolean; params?: URLSearchParams }): string {
  const encodedVideoId = encodeURIComponent(videoId);
  const useLegacy = options?.forceLegacy ?? DEFAULT_REPORT_VIEW === 'legacy';
  const basePath = useLegacy ? `/videos/${encodedVideoId}` : `/videos/${encodedVideoId}/timeline-report`;
  const queryString = options?.params?.toString();
  return queryString ? `${basePath}?${queryString}` : basePath;
}

// -- Session helpers (from AnalystPage) ------------------------------------

function getInitials(s: AnalystSession): string {
  const name = (s.participant_demographics as Record<string, unknown> | null)
    ?.name as string | undefined;
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2)
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    if (parts[0]?.length >= 2) return parts[0].slice(0, 2).toUpperCase();
  }
  const ext = s.participant_external_id;
  if (ext && ext.length >= 2) return ext.slice(0, 2).toUpperCase();
  return '??';
}

function renderStars(value: number | null | undefined, max = 5): string {
  if (value == null) return '\u2014';
  const filled = Math.round(value);
  return (
    '\u2605'.repeat(Math.min(filled, max)) +
    '\u2606'.repeat(Math.max(max - filled, 0))
  );
}

function getSurveyScore(s: AnalystSession, key: string): number | null {
  const r = s.survey_responses.find((sr) => sr.question_key === key);
  return r?.response_number ?? null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
}

const AVATAR_COLORS = [
  '#c8f031', '#31d0f0', '#f06131', '#a78bfa',
  '#f0c831', '#31f0a5', '#f031a5', '#6bb8ff',
];

function avatarColor(index: number): string {
  return AVATAR_COLORS[index % AVATAR_COLORS.length];
}

function getCatalogInitials(s: VideoCatalogSession): string {
  const name = (s.participant_demographics as Record<string, unknown> | null)
    ?.name as string | undefined;
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2)
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    if (parts[0]?.length >= 2) return parts[0].slice(0, 2).toUpperCase();
  }
  const ext = s.participant_external_id;
  if (ext && ext.length >= 2) return ext.slice(0, 2).toUpperCase();
  return '??';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function HomePage() {
  const navigate = useNavigate();
  const [videoInput, setVideoInput] = useState(DEFAULT_VIDEO_ID);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<VideoCatalogItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortKey, setSortKey] = useState<'newest' | 'oldest' | 'alpha' | 'sessions'>('newest');
  const [visibleCount, setVisibleCount] = useState(20);

  // Session expansion state
  const [expandedVideoId, setExpandedVideoId] = useState<string | null>(null);
  const [sessionsData, setSessionsData] = useState<AnalystSessionsResponse | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [sessionSearch, setSessionSearch] = useState('');

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const resolution = resolveHomeInput(videoInput);
    if (!resolution) {
      setError('Enter a readout URL or video ID.');
      return;
    }

    setError(null);
    if (resolution.type === 'predictor') {
      const params = new URLSearchParams({
        video_url: resolution.videoUrl
      });
      navigate(`/predictor?${params.toString()}`);
      return;
    }

    navigate(buildVideoReportPath(resolution.videoId));
  };

  // Load catalog — extracted so the retry button can re-invoke it.
  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);

    try {
      const response = await fetchVideoCatalog(100);
      setCatalog(response ?? []);
    } catch (err) {
      setCatalogError(err instanceof Error ? err.message : 'Failed to load recordings catalog.');
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCatalog();
  }, [loadCatalog]);

  // Load sessions when a video is expanded
  useEffect(() => {
    if (!expandedVideoId) {
      setSessionsData(null);
      setSessionsError(null);
      setSessionSearch('');
      return;
    }

    let cancelled = false;
    setSessionsLoading(true);
    setSessionsError(null);
    setSessionSearch('');

    fetchAnalystSessions(expandedVideoId)
      .then((data) => {
        if (!cancelled) {
          setSessionsData(data);
          setSessionsLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setSessionsError(err.message);
          setSessionsLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [expandedVideoId]);

  const displayedCatalog = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const filtered = q
      ? catalog.filter(
          (item) =>
            item.title.toLowerCase().includes(q) ||
            item.study_name.toLowerCase().includes(q) ||
            item.video_id.toLowerCase().includes(q)
        )
      : catalog;

    const sorted = [...filtered].sort((a, b) => {
      if (sortKey === 'newest') return Date.parse(b.created_at) - Date.parse(a.created_at);
      if (sortKey === 'oldest') return Date.parse(a.created_at) - Date.parse(b.created_at);
      if (sortKey === 'sessions') return b.sessions_count - a.sessions_count;
      return a.title.localeCompare(b.title);
    });

    return { all: sorted, visible: sorted.slice(0, visibleCount), hasMore: sorted.length > visibleCount };
  }, [catalog, searchQuery, sortKey, visibleCount]);

  // Filtered sessions for expanded card
  const filteredSessions = useMemo(() => {
    if (!sessionsData?.sessions) return [];
    if (!sessionSearch.trim()) return sessionsData.sessions;
    const q = sessionSearch.trim().toLowerCase();
    return sessionsData.sessions.filter((s) => {
      const initials = getInitials(s).toLowerCase();
      const extId = (s.participant_external_id ?? '').toLowerCase();
      const name = (
        ((s.participant_demographics as Record<string, unknown> | null)?.name as string) ?? ''
      ).toLowerCase();
      return initials.includes(q) || extId.includes(q) || name.includes(q);
    });
  }, [sessionsData, sessionSearch]);

  // Aggregate stats for expanded card
  const aggregateStats = useMemo(() => {
    const sessions = sessionsData?.sessions ?? [];
    if (sessions.length === 0) return null;

    const engagementScores = sessions
      .map((s) => getSurveyScore(s, 'overall_interest_likert'))
      .filter((v): v is number => v != null);
    const clarityScores = sessions
      .map((s) => getSurveyScore(s, 'recall_comprehension_likert'))
      .filter((v): v is number => v != null);

    const avg = (arr: number[]) =>
      arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : null;

    return {
      total: sessions.length,
      avgEngagement: avg(engagementScores),
      avgClarity: avg(clarityScores),
    };
  }, [sessionsData]);

  const handleDelete = async (item: VideoCatalogItem) => {
    if (!window.confirm(`Delete "${item.title}" and all its recordings? This cannot be undone.`)) {
      return;
    }
    setDeletingId(item.video_id);
    try {
      await deleteVideo(item.video_id);
      setCatalog((prev) => prev.filter((v) => v.video_id !== item.video_id));
      if (expandedVideoId === item.video_id) setExpandedVideoId(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed.');
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSessions = (videoId: string) => {
    setExpandedVideoId((prev) => (prev === videoId ? null : videoId));
  };

  // -------------------------------------------------------------------------
  // Inline sessions panel (rendered inside expanded video card)
  // -------------------------------------------------------------------------

  function renderSessionsPanel(videoId: string) {
    if (expandedVideoId !== videoId) return null;

    return (
      <>
        <Divider sx={{ my: 1 }} />

        {/* Aggregate bar */}
        {sessionsData && aggregateStats && (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              px: 2,
              py: 1.5,
              bgcolor: '#111118',
              borderRadius: '8px',
              border: '1px solid #26262f',
              flexWrap: 'wrap',
              mb: 1.5,
            }}
          >
            <Typography
              sx={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: '0.8rem',
                color: '#c8f031',
                fontWeight: 600,
              }}
            >
              {aggregateStats.total} session{aggregateStats.total !== 1 ? 's' : ''}
            </Typography>
            {aggregateStats.avgEngagement != null && (
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: '0.8rem',
                  color: '#8a8895',
                }}
              >
                Avg Engagement{' '}
                <Box component="span" sx={{ color: '#e8e6e3' }}>
                  {renderStars(Math.round(aggregateStats.avgEngagement))}{' '}
                  {aggregateStats.avgEngagement.toFixed(1)}
                </Box>
              </Typography>
            )}
            {aggregateStats.avgClarity != null && (
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: '0.8rem',
                  color: '#8a8895',
                }}
              >
                Avg Clarity{' '}
                <Box component="span" sx={{ color: '#e8e6e3' }}>
                  {renderStars(Math.round(aggregateStats.avgClarity))}{' '}
                  {aggregateStats.avgClarity.toFixed(1)}
                </Box>
              </Typography>
            )}
            <Box sx={{ flexGrow: 1 }} />
            {sessionsData.last_updated_at && (
              <Typography
                sx={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: '0.72rem',
                  color: '#5a5a68',
                }}
              >
                Last update: {formatDateTime(sessionsData.last_updated_at)}
              </Typography>
            )}
          </Box>
        )}

        {/* Session search */}
        {sessionsData && sessionsData.sessions.length > 0 && (
          <TextField
            size="small"
            placeholder="Search sessions by name or ID\u2026"
            value={sessionSearch}
            onChange={(e) => setSessionSearch(e.target.value)}
            fullWidth
            sx={{
              mb: 1.5,
              '& .MuiOutlinedInput-root': {
                bgcolor: '#111118',
                color: '#e8e6e3',
                fontFamily: '"DM Sans", sans-serif',
                fontSize: '0.85rem',
                '& fieldset': { borderColor: '#26262f' },
                '&:hover fieldset': { borderColor: '#3a3a48' },
                '&.Mui-focused fieldset': { borderColor: '#c8f031' },
              },
            }}
          />
        )}

        {/* Loading */}
        {sessionsLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
            <CircularProgress size={24} sx={{ color: '#c8f031' }} />
          </Box>
        )}

        {/* Error */}
        {sessionsError && (
          <Typography
            sx={{ color: '#f06131', textAlign: 'center', py: 2, fontSize: '0.85rem' }}
          >
            Failed to load sessions
          </Typography>
        )}

        {/* Empty */}
        {!sessionsLoading && !sessionsError && sessionsData && filteredSessions.length === 0 && (
          <Typography
            sx={{
              textAlign: 'center',
              color: '#5a5a68',
              py: 3,
              fontFamily: '"DM Sans", sans-serif',
              fontSize: '0.9rem',
            }}
          >
            {sessionSearch ? 'No sessions match your search.' : 'No sessions found for this video.'}
          </Typography>
        )}

        {/* Session cards grid */}
        {!sessionsLoading && filteredSessions.length > 0 && (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 1.5,
            }}
          >
            {filteredSessions.map((session, idx) => {
              const initials = getInitials(session);
              const engagement = getSurveyScore(session, 'overall_interest_likert');
              const clarity = getSurveyScore(session, 'recall_comprehension_likert');
              const color = avatarColor(idx);

              return (
                <Card
                  key={session.session_id}
                  sx={{
                    bgcolor: '#111118',
                    border: '1px solid #26262f',
                    borderRadius: '10px',
                    transition: 'border-color 0.15s, box-shadow 0.15s',
                    '&:hover': {
                      borderColor: '#c8f031',
                      boxShadow: '0 0 12px rgba(200,240,49,0.08)',
                    },
                  }}
                >
                  <CardActionArea
                    onClick={() => navigate(`/videos/${videoId}?session_id=${session.session_id}`)}
                    sx={{ p: 2, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1.2 }}
                  >
                    {/* Avatar + status row */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                      <Box
                        sx={{
                          width: 38,
                          height: 38,
                          borderRadius: '50%',
                          bgcolor: `${color}18`,
                          border: `2px solid ${color}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: '"JetBrains Mono", monospace',
                          fontWeight: 700,
                          fontSize: '0.8rem',
                          color,
                          flexShrink: 0,
                        }}
                      >
                        {initials}
                      </Box>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontSize: '0.7rem',
                          color:
                            session.status === 'completed'
                              ? '#c8f031'
                              : session.status === 'abandoned'
                              ? '#f06131'
                              : '#8a8895',
                          textTransform: 'uppercase',
                          letterSpacing: '0.06em',
                          fontWeight: 600,
                        }}
                      >
                        {session.status}
                      </Typography>
                    </Box>

                    {/* Star ratings */}
                    <Box sx={{ width: '100%' }}>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontSize: '0.75rem',
                          color: '#e8e6e3',
                          lineHeight: 1.6,
                        }}
                      >
                        {renderStars(engagement)}
                      </Typography>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontSize: '0.75rem',
                          color: '#e8e6e3',
                          lineHeight: 1.6,
                        }}
                      >
                        {renderStars(clarity)}
                      </Typography>
                    </Box>

                    {/* Date + time */}
                    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, width: '100%' }}>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontSize: '0.7rem',
                          color: '#5a5a68',
                        }}
                      >
                        {formatDate(session.created_at)}
                      </Typography>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono", monospace',
                          fontSize: '0.7rem',
                          color: '#3a3a48',
                        }}
                      >
                        {formatTime(session.created_at)}
                      </Typography>
                    </Box>
                  </CardActionArea>
                </Card>
              );
            })}
          </Box>
        )}
      </>
    );
  }

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1100, mx: 'auto' }}>
      <Stack spacing={2}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h4" fontWeight={700}>
                NeuroTrace Analyst View
              </Typography>
              <Typography color="text.secondary">
                Open analytics from a readout URL or video ID. For URL-based prelaunch estimates, open Predictor Lab.
              </Typography>
              <Typography color="text.secondary" variant="body2">
                External ad URLs open Predictor Lab automatically.
              </Typography>
              <Typography color="text.secondary" variant="body2">
                Timeline report is the default entry point; legacy deep-dive reporting remains available.
              </Typography>

              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <Button variant="outlined" onClick={() => navigate('/predictor')} data-testid="open-predictor-button">
                  Open Predictor Lab
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => navigate('/observability')}
                  data-testid="open-observability-button"
                >
                  Open Observability
                </Button>
              </Stack>

              <Box component="form" onSubmit={onSubmit}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <TextField
                    label="Readout URL or Video ID"
                    fullWidth
                    value={videoInput}
                    placeholder="e.g. https://.../videos/<id> or <id>"
                    onChange={(event) => setVideoInput(event.target.value)}
                    inputProps={{ 'data-testid': 'video-id-input' }}
                  />
                  <Button type="submit" variant="contained" data-testid="open-video-button">
                    Open
                  </Button>
                </Stack>
              </Box>

              {error ? <Alert severity="warning">{error}</Alert> : null}
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Stack spacing={1.5}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ xs: 'flex-start', sm: 'center' }} justifyContent="space-between">
                <Typography variant="h5" fontWeight={700}>
                  Recordings Catalog
                  {!catalogLoading && !catalogError && catalog.length > 0
                    ? ` (${displayedCatalog.all.length}${displayedCatalog.all.length !== catalog.length ? ` / ${catalog.length}` : ''})`
                    : ''}
                </Typography>
                <Stack direction="row" spacing={1}>
                  {(['newest', 'oldest', 'alpha', 'sessions'] as const).map((key) => (
                    <Button
                      key={key}
                      size="small"
                      variant={sortKey === key ? 'contained' : 'outlined'}
                      onClick={() => { setSortKey(key); setVisibleCount(20); }}
                    >
                      {key === 'newest' ? 'Newest' : key === 'oldest' ? 'Oldest' : key === 'alpha' ? 'A\u2013Z' : 'Sessions'}
                    </Button>
                  ))}
                </Stack>
              </Stack>
              <Typography color="text.secondary">
                Click a session count to browse individual respondent sessions.
              </Typography>
              <TextField
                size="small"
                placeholder="Search by title, study, or video ID\u2026"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setVisibleCount(20); }}
                fullWidth
              />

              {catalogLoading ? (
                <Stack direction="row" spacing={1} alignItems="center" data-testid="catalog-loading">
                  <CircularProgress size={20} />
                  <Typography color="text.secondary">Loading recordings\u2026</Typography>
                </Stack>
              ) : null}

              {catalogError ? (
                <RetryAlert
                  message={catalogError}
                  onRetry={loadCatalog}
                  data-testid="catalog-error"
                />
              ) : null}

              {!catalogLoading && !catalogError && catalog.length === 0 ? (
                <Alert severity="info" data-testid="catalog-empty">
                  No recordings yet. Complete one watchlab session and this catalog will populate.
                </Alert>
              ) : null}

              {!catalogLoading && !catalogError && catalog.length > 0 && displayedCatalog.all.length === 0 ? (
                <Alert severity="info">No recordings match your search.</Alert>
              ) : null}

              {!catalogLoading && !catalogError
                ? displayedCatalog.visible.map((item) => {
                    const isExpanded = expandedVideoId === item.video_id;

                    return (
                      <Card
                        key={item.video_id}
                        variant="outlined"
                        sx={{
                          borderRadius: 2,
                          borderColor: isExpanded ? '#c8f031' : undefined,
                          transition: 'border-color 0.15s',
                        }}
                        data-testid="catalog-recording-card"
                      >
                        <CardContent>
                          <Stack spacing={1}>
                            <Stack
                              direction={{ xs: 'column', md: 'row' }}
                              spacing={1}
                              justifyContent="space-between"
                              alignItems={{ xs: 'flex-start', md: 'center' }}
                            >
                              <Box>
                                <Typography variant="h6" fontWeight={700}>
                                  {item.title}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  Video ID: {item.video_id}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  Study: {item.study_name}
                                  {item.last_session_at
                                    ? ` · Last session: ${formatDateTime(item.last_session_at)}`
                                    : ` · Created: ${formatDate(item.created_at)}`}
                                </Typography>
                                {/* Respondent initials */}
                                {item.recent_sessions.length > 0 && (
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                    {item.recent_sessions.map((rs, idx) => (
                                      <Box
                                        key={rs.id}
                                        sx={{
                                          width: 26,
                                          height: 26,
                                          borderRadius: '50%',
                                          bgcolor: `${avatarColor(idx)}18`,
                                          border: `1.5px solid ${avatarColor(idx)}`,
                                          display: 'flex',
                                          alignItems: 'center',
                                          justifyContent: 'center',
                                          fontFamily: '"JetBrains Mono", monospace',
                                          fontWeight: 700,
                                          fontSize: '0.6rem',
                                          color: avatarColor(idx),
                                          flexShrink: 0,
                                        }}
                                        title={`${getCatalogInitials(rs)} · ${rs.status} · ${formatDateTime(rs.created_at)}`}
                                      >
                                        {getCatalogInitials(rs)}
                                      </Box>
                                    ))}
                                    {item.sessions_count > item.recent_sessions.length && (
                                      <Typography
                                        sx={{
                                          fontFamily: '"JetBrains Mono", monospace',
                                          fontSize: '0.65rem',
                                          color: '#5a5a68',
                                          ml: 0.5,
                                        }}
                                      >
                                        +{item.sessions_count - item.recent_sessions.length} more
                                      </Typography>
                                    )}
                                  </Box>
                                )}
                              </Box>
                              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Button
                                  variant="contained"
                                  onClick={() => navigate(buildVideoReportPath(item.video_id))}
                                  data-testid="catalog-open-aggregate"
                                >
                                  Open Report
                                </Button>
                                <Button
                                  variant="outlined"
                                  onClick={() => navigate(`/videos/${item.video_id}/timeline-report`)}
                                  data-testid="catalog-open-timeline-report"
                                >
                                  Open Timeline
                                </Button>
                                <Button
                                  variant="outlined"
                                  color="error"
                                  disabled={deletingId === item.video_id}
                                  onClick={() => void handleDelete(item)}
                                  data-testid="catalog-delete-video"
                                >
                                  {deletingId === item.video_id ? 'Deleting\u2026' : 'Delete'}
                                </Button>
                              </Stack>
                            </Stack>

                            <Divider />

                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                              <Chip
                                label={`${isExpanded ? '\u25B2' : '\u25BC'} Sessions ${item.sessions_count}`}
                                onClick={() => toggleSessions(item.video_id)}
                                clickable
                                color={isExpanded ? 'primary' : 'default'}
                                sx={{
                                  cursor: 'pointer',
                                  fontWeight: 600,
                                  ...(isExpanded && {
                                    bgcolor: '#c8f031',
                                    color: '#08080a',
                                    '&:hover': { bgcolor: '#b8e028' },
                                  }),
                                }}
                              />
                              <Chip label={`Completed ${item.completed_sessions_count}`} color={item.completed_sessions_count > 0 ? 'success' : 'default'} />
                              {item.abandoned_sessions_count > 0 ? (
                                <Chip label={`Abandoned ${item.abandoned_sessions_count}`} color="warning" />
                              ) : null}
                              <Chip label={`Participants ${item.participants_count}`} />
                              {item.duration_ms ? <Chip label={`Duration ${(item.duration_ms / 1000).toFixed(1)}s`} /> : null}
                              {!item.source_url ? (
                                <Chip label="No video source" variant="outlined" color="default" data-testid="catalog-no-source-url" />
                              ) : null}
                              {item.sessions_count === 0 ? (
                                <Chip label="No recordings yet" variant="outlined" />
                              ) : item.abandoned_sessions_count === item.sessions_count ? (
                                <Chip label="All sessions abandoned" color="warning" variant="outlined" />
                              ) : null}
                            </Stack>

                            {/* Inline sessions panel */}
                            {renderSessionsPanel(item.video_id)}
                          </Stack>
                        </CardContent>
                      </Card>
                    );
                  })
                : null}

              {!catalogLoading && !catalogError && displayedCatalog.hasMore ? (
                <Button
                  variant="outlined"
                  onClick={() => setVisibleCount((n) => n + 20)}
                  data-testid="catalog-load-more"
                >
                  Load more ({displayedCatalog.all.length - visibleCount} remaining)
                </Button>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
