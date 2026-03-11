import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { reportFrontendDiagnosticFireAndForget } from '../api';

interface Props {
  children: ReactNode;
  /** When this value changes, the error state is auto-cleared (e.g. on route change). */
  resetKey?: string;
  /** If provided, renders a "Try Again" button instead of a full-page reload. */
  onRetry?: () => void;
  /** Diagnostic label included in telemetry (e.g. route name). */
  label?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidUpdate(prevProps: Props): void {
    // Auto-clear error when resetKey changes (e.g. user navigated to a different route).
    if (this.props.resetKey !== prevProps.resetKey && this.state.hasError) {
      this.setState({ hasError: false, error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary] Uncaught error:', error, info.componentStack);

    reportFrontendDiagnosticFireAndForget({
      surface: 'dashboard',
      page: 'unknown',
      severity: 'error',
      event_type: 'error_boundary_catch',
      message: error.message?.slice(0, 500),
      context: {
        label: this.props.label ?? 'root',
        stack: (info.componentStack ?? '').slice(0, 1000),
      },
    });
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onRetry?.();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          gap: 2,
          px: 3,
          textAlign: 'center',
        }}
      >
        <Typography
          sx={{
            fontFamily: '"DM Sans", sans-serif',
            fontWeight: 700,
            fontSize: '1.25rem',
            color: '#e8e6e3',
          }}
        >
          Something went wrong
        </Typography>
        <Typography
          sx={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: '0.78rem',
            color: '#8a8895',
            maxWidth: 600,
            wordBreak: 'break-word',
          }}
        >
          {this.state.error?.message ?? 'An unexpected error occurred.'}
        </Typography>
        {this.props.onRetry ? (
          <Button
            variant="outlined"
            size="small"
            onClick={this.handleRetry}
            sx={{
              mt: 1,
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: '0.72rem',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: '#c8f031',
              borderColor: '#c8f031',
              '&:hover': { borderColor: '#e8e6e3', color: '#e8e6e3' },
            }}
          >
            Try Again
          </Button>
        ) : (
          <Button
            variant="outlined"
            size="small"
            onClick={() => window.location.reload()}
            sx={{
              mt: 1,
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: '0.72rem',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: '#c8f031',
              borderColor: '#c8f031',
              '&:hover': { borderColor: '#e8e6e3', color: '#e8e6e3' },
            }}
          >
            Reload Page
          </Button>
        )}
      </Box>
    );
  }
}
