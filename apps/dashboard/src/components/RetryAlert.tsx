import { Alert, Button } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';

interface RetryAlertProps {
  message: string;
  onRetry?: () => void;
  'data-testid'?: string;
}

/**
 * Error alert with an optional "Retry" action button.
 *
 * Drop-in replacement for `<Alert severity="error">{msg}</Alert>` that gives
 * users a one-click recovery path instead of forcing a full page reload.
 */
export default function RetryAlert({ message, onRetry, 'data-testid': testId }: RetryAlertProps) {
  return (
    <Alert
      severity="error"
      data-testid={testId}
      action={
        onRetry ? (
          <Button
            color="inherit"
            size="small"
            startIcon={<RefreshIcon />}
            onClick={onRetry}
            sx={{
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: '0.72rem',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
            }}
          >
            Retry
          </Button>
        ) : undefined
      }
    >
      {message}
    </Alert>
  );
}
