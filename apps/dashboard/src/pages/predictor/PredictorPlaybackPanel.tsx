import { RefObject } from 'react';
import {
  Alert,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  Typography
} from '@mui/material';
import type { PredictorTimelineEvent } from '../../utils/predictorTimeline';
import { formatSeconds } from '../../utils/predictorTimeline';

export type PredictorPlaybackPanelProps = {
  videoRef: RefObject<HTMLVideoElement | null>;
  playbackVideoUrl: string | null;
  playbackError: string | null;
  timelineEvents: PredictorTimelineEvent[];
  onTimeUpdate: (currentTime: number) => void;
  onVideoReady: () => void;
  onVideoError: () => void;
  onSeek: (seconds: number) => void;
};

export default function PredictorPlaybackPanel({
  videoRef,
  playbackVideoUrl,
  playbackError,
  timelineEvents,
  onTimeUpdate,
  onVideoReady,
  onVideoError,
  onSeek
}: PredictorPlaybackPanelProps) {
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, lg: 7 }}>
        <Stack spacing={1.25}>
          <Typography variant="h6" fontWeight={700}>
            Prediction playback
          </Typography>
          {playbackVideoUrl ? (
            <video
              ref={videoRef}
              src={playbackVideoUrl}
              controls
              width="100%"
              onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
              onLoadedMetadata={onVideoReady}
              onCanPlay={onVideoReady}
              onError={onVideoError}
              data-testid="predictor-video-player"
            />
          ) : (
            <Alert severity="info" data-testid="predictor-video-unavailable">
              Playback preview is unavailable for this URL. Provide a direct video file URL for synced
              timeline preview.
            </Alert>
          )}
          <Typography variant="body2" color="text.secondary">
            Click the timeline or a key event to seek this player.
          </Typography>
          {playbackError ? (
            <Alert severity="error" data-testid="predictor-video-playback-error">
              {playbackError}
            </Alert>
          ) : null}
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, lg: 5 }}>
        <Stack spacing={1}>
          <Typography variant="h6" fontWeight={700}>
            Key Events
          </Typography>
          <Divider />
          {timelineEvents.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No key events were generated.
            </Typography>
          ) : (
            <List dense>
              {timelineEvents.map((event) => (
                <ListItem disablePadding key={event.id}>
                  <ListItemButton
                    onClick={() => onSeek(event.tSec)}
                    data-testid={`predictor-event-${event.id}`}
                  >
                    <ListItemText
                      primary={`${formatSeconds(event.tSec)} \u2022 ${event.title}`}
                      secondary={event.secondary}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          )}
        </Stack>
      </Grid>
    </Grid>
  );
}
