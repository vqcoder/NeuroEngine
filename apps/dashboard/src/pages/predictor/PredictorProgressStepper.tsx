import {
  Alert,
  Button,
  CircularProgress,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Typography
} from '@mui/material';
import type { PredictJobStatus } from '../../types';

export type PredictorProgressStepperProps = {
  inputTab: 'url' | 'file';
  jobStatus: PredictJobStatus | null;
  elapsed: number;
  slowLoad: boolean;
  onCancel: () => void;
};

export default function PredictorProgressStepper({
  inputTab,
  jobStatus,
  elapsed,
  slowLoad,
  onCancel
}: PredictorProgressStepperProps) {
  return (
    <Stack spacing={1.5} data-testid="predictor-loading">
      {inputTab === 'url' ? (
        <Stepper
          activeStep={
            { pending: 0, downloading: 1, running: 2, uploading: 3, done: 4, failed: 4 }[
              jobStatus?.status ?? 'pending'
            ] ?? 0
          }
          alternativeLabel
        >
          {['Queued', 'Downloading', 'Analyzing', 'Storing', 'Complete'].map((label) => (
            <Step key={label}><StepLabel>{label}</StepLabel></Step>
          ))}
        </Stepper>
      ) : (
        <Stepper
          activeStep={
            !jobStatus ? 0
              : ({ pending: 1, running: 2, uploading: 3, done: 4, failed: 4 } as Record<string, number>)[jobStatus.status] ?? 1
          }
          alternativeLabel
        >
          {['Uploading file', 'Queued', 'Analyzing', 'Storing', 'Complete'].map((label) => (
            <Step key={label}><StepLabel>{label}</StepLabel></Step>
          ))}
        </Stepper>
      )}
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={20} />
          <Typography color="text.secondary">
            {jobStatus?.stage_label ?? (inputTab === 'file' ? 'Uploading file to server\u2026' : 'Queued\u2026')}
            {elapsed > 0 ? ` (${elapsed}s)` : ''}
          </Typography>
        </Stack>
        <Button size="small" variant="outlined" color="inherit" onClick={onCancel}>
          Cancel
        </Button>
      </Stack>
      {slowLoad ? (
        <Alert severity="info" data-testid="predictor-slow-load">
          Still working — large videos can take up to 2 minutes to download and process.
        </Alert>
      ) : null}
    </Stack>
  );
}
