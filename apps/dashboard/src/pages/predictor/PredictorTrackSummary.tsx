import {
  Card,
  CardContent,
  Grid,
  Typography
} from '@mui/material';
import type { TimelineTrack } from '../../utils/timelineReport';

export type PredictorTrackSummaryProps = {
  tracks: TimelineTrack[];
};

export default function PredictorTrackSummary({ tracks }: PredictorTrackSummaryProps) {
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>
          Track Evidence Window Summary
        </Typography>
        <Grid container spacing={1.25}>
          {tracks.map((track) => (
            <Grid key={track.key} size={{ xs: 12, md: 6, lg: 4 }}>
              <Card variant="outlined" data-testid={`predictor-track-summary-${track.key}`}>
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
  );
}
