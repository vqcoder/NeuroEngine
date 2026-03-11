import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControlLabel,
  FormGroup,
  Grid,
  Stack,
  Switch,
  Tooltip,
  Typography
} from '@mui/material';
import type {
  ReadoutCut,
  ReadoutScene
} from '../types';
import type {
  TimelineKeyMoment,
  TimelineTrack,
  TimelineTrackKey,
  TimelineTrackVisibility
} from '../utils/timelineReport';

type TimelineTrackLanesProps = {
  durationMs: number;
  scenes: ReadoutScene[];
  cuts: ReadoutCut[];
  tracks: TimelineTrack[];
  visibility: TimelineTrackVisibility;
  onToggleTrack: (trackKey: TimelineTrackKey) => void;
  onSeek: (seconds: number) => void;
  keyMoments: TimelineKeyMoment[];
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function toLeftPercent(durationMs: number, valueMs: number): number {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return 0;
  }
  return clamp((valueMs / durationMs) * 100, 0, 100);
}

function toWidthPercent(durationMs: number, startMs: number, endMs: number): number {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return 0;
  }
  const normalizedStart = clamp(startMs, 0, durationMs);
  const normalizedEnd = clamp(endMs, 0, durationMs);
  const raw = ((normalizedEnd - normalizedStart) / durationMs) * 100;
  return clamp(raw, 0.6, 100);
}

function formatWindowLabel(startMs: number, endMs: number): string {
  const startSec = (startMs / 1000).toFixed(1);
  const endSec = (endMs / 1000).toFixed(1);
  return `${startSec}s-${endSec}s`;
}

export default function TimelineTrackLanes({
  durationMs,
  scenes,
  cuts,
  tracks,
  visibility,
  onToggleTrack,
  onSeek,
  keyMoments
}: TimelineTrackLanesProps) {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return (
      <Card data-testid="timeline-track-lanes-card">
        <CardContent>
          <Alert severity="warning">Timeline lanes are unavailable because duration is missing.</Alert>
        </CardContent>
      </Card>
    );
  }

  const visibleTracks = tracks.filter((track) => visibility[track.key]);
  const eventBoundaryLines = keyMoments.filter((moment) => moment.type === 'event_boundary');

  return (
    <Card data-testid="timeline-track-lanes-card">
      <CardContent>
        <Stack spacing={2}>
          <Box>
            <Typography variant="h6" fontWeight={700}>
              Scene-by-Scene Timeline Layers
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Toggle claim-safe score tracks to inspect where each diagnostic is supported on the timeline.
            </Typography>
          </Box>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 4 }}>
              <Typography variant="subtitle2" fontWeight={700} gutterBottom>
                Score tracks
              </Typography>
              <FormGroup data-testid="timeline-track-toggles">
                {tracks.map((track) => (
                  <FormControlLabel
                    key={track.key}
                    control={
                      <Switch
                        size="small"
                        checked={visibility[track.key]}
                        onChange={() => onToggleTrack(track.key)}
                        data-testid={`timeline-track-toggle-${track.key}`}
                      />
                    }
                    label={
                      <Stack spacing={0}>
                        <Typography variant="body2" fontWeight={600}>
                          {track.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {track.description}
                        </Typography>
                      </Stack>
                    }
                    sx={{ alignItems: 'flex-start', my: 0.35 }}
                  />
                ))}
              </FormGroup>
            </Grid>

            <Grid size={{ xs: 12, md: 8 }}>
              <Stack spacing={1.25} data-testid="timeline-track-lane-group">
                <Box data-testid="timeline-scenes-lane">
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.4 }}>
                    Scenes
                  </Typography>
                  <Box
                    sx={{
                      position: 'relative',
                      height: 28,
                      borderRadius: 1,
                      border: '1px solid rgba(255,255,255,0.12)',
                      overflow: 'hidden',
                      bgcolor: 'rgba(255,255,255,0.02)'
                    }}
                  >
                    {scenes.map((scene, index) => {
                      const left = toLeftPercent(durationMs, scene.start_ms);
                      const width = toWidthPercent(durationMs, scene.start_ms, scene.end_ms);
                      return (
                        <Tooltip
                          key={`scene-lane-${scene.scene_index}-${scene.start_ms}`}
                          title={`${scene.label ?? `Scene ${scene.scene_index + 1}`} (${formatWindowLabel(
                            scene.start_ms,
                            scene.end_ms
                          )})`}
                        >
                          <Box
                            onClick={() => onSeek(scene.start_ms / 1000)}
                            sx={{
                              position: 'absolute',
                              top: 0,
                              bottom: 0,
                              left: `${left}%`,
                              width: `${width}%`,
                              cursor: 'pointer',
                              borderRight: '1px solid rgba(255,255,255,0.14)',
                              bgcolor: index % 2 === 0 ? 'rgba(47,125,255,0.18)' : 'rgba(88,212,193,0.18)'
                            }}
                            data-testid={`timeline-scene-window-${index}`}
                          >
                            <Typography
                              variant="caption"
                              sx={{
                                px: 0.5,
                                color: '#e8edf3',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis'
                              }}
                            >
                              {scene.label ?? `S${scene.scene_index + 1}`}
                            </Typography>
                          </Box>
                        </Tooltip>
                      );
                    })}
                  </Box>
                </Box>

                <Box data-testid="timeline-key-moments-lane">
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.4 }}>
                    <Typography variant="caption" color="text.secondary">
                      Key moments
                    </Typography>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={`Cuts ${cuts.length}`} />
                      <Chip size="small" label={`Markers ${keyMoments.length}`} />
                    </Stack>
                  </Stack>
                  <Box
                    sx={{
                      position: 'relative',
                      height: 24,
                      borderRadius: 1,
                      border: '1px solid rgba(255,255,255,0.12)',
                      bgcolor: 'rgba(255,255,255,0.01)'
                    }}
                  >
                    {keyMoments.map((moment, index) => {
                      const left = toLeftPercent(durationMs, moment.start_ms);
                      const width = toWidthPercent(durationMs, moment.start_ms, moment.end_ms);
                      return (
                        <Tooltip
                          key={`timeline-key-moment-${moment.type}-${moment.start_ms}-${index}`}
                          title={`${moment.label}: ${moment.reason}`}
                        >
                          <Box
                            onClick={() => onSeek(moment.start_ms / 1000)}
                            sx={{
                              position: 'absolute',
                              top: 2,
                              bottom: 2,
                              left: `${left}%`,
                              width: `${width}%`,
                              borderRadius: 0.7,
                              cursor: 'pointer',
                              bgcolor: moment.color,
                              opacity: moment.type === 'event_boundary' ? 0.65 : 0.85
                            }}
                            data-testid={`timeline-key-moment-${moment.type}-${index}`}
                          />
                        </Tooltip>
                      );
                    })}
                  </Box>
                </Box>

                <Divider sx={{ borderStyle: 'dashed' }} />

                {visibleTracks.length === 0 ? (
                  <Alert severity="info">Enable at least one track to view timeline evidence windows.</Alert>
                ) : (
                  visibleTracks.map((track) => (
                    <Box key={track.key} data-testid={`timeline-track-row-${track.key}`}>
                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        justifyContent="space-between"
                        alignItems={{ xs: 'flex-start', sm: 'center' }}
                        sx={{ mb: 0.4 }}
                        spacing={0.5}
                      >
                        <Typography variant="body2" fontWeight={700} sx={{ color: track.color }}>
                          {track.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {track.windows.length} evidence window{track.windows.length === 1 ? '' : 's'}
                        </Typography>
                      </Stack>
                      <Box
                        sx={{
                          position: 'relative',
                          height: 28,
                          borderRadius: 1,
                          border: '1px solid rgba(255,255,255,0.12)',
                          bgcolor: 'rgba(255,255,255,0.01)'
                        }}
                      >
                        {eventBoundaryLines.map((boundary, index) => {
                          const left = toLeftPercent(durationMs, boundary.start_ms);
                          return (
                            <Box
                              key={`boundary-${track.key}-${boundary.start_ms}-${index}`}
                              sx={{
                                position: 'absolute',
                                left: `${left}%`,
                                top: 0,
                                bottom: 0,
                                width: 1,
                                bgcolor: 'rgba(255,255,255,0.2)'
                              }}
                            />
                          );
                        })}

                        {track.windows.map((window, index) => {
                          const left = toLeftPercent(durationMs, window.start_ms);
                          const width = toWidthPercent(durationMs, window.start_ms, window.end_ms);
                          const subtitle = [
                            formatWindowLabel(window.start_ms, window.end_ms),
                            window.score !== null && window.score !== undefined
                              ? `score ${window.score.toFixed(1)}`
                              : null,
                            window.confidence !== null && window.confidence !== undefined
                              ? `confidence ${(window.confidence * 100).toFixed(0)}%`
                              : null,
                            window.source
                          ]
                            .filter(Boolean)
                            .join(' • ');

                          return (
                            <Tooltip
                              key={`window-${track.key}-${window.start_ms}-${window.end_ms}-${index}`}
                              title={`${window.reason} (${subtitle})`}
                            >
                              <Box
                                onClick={() => onSeek(window.start_ms / 1000)}
                                sx={{
                                  position: 'absolute',
                                  top: 3,
                                  bottom: 3,
                                  left: `${left}%`,
                                  width: `${width}%`,
                                  borderRadius: 0.7,
                                  cursor: 'pointer',
                                  bgcolor: track.color,
                                  opacity: 0.86,
                                  boxShadow: '0 0 0 1px rgba(8,11,15,0.45) inset'
                                }}
                                data-testid={`timeline-track-window-${track.key}-${index}`}
                              />
                            </Tooltip>
                          );
                        })}
                      </Box>
                    </Box>
                  ))
                )}
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      </CardContent>
    </Card>
  );
}
