import { useState, type ReactNode } from 'react';
import { Route, Routes, Link, useLocation } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import ErrorBoundary from './components/ErrorBoundary';
import { useAuth } from './hooks/useAuth';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import ObservabilityPage from './pages/ObservabilityPage';
import PredictorPage from './pages/PredictorPage';
import StudiesPage from './pages/StudiesPage';
import StudyDetailPage from './pages/StudyDetailPage';
import VideoDashboardPage from './pages/VideoDashboardPage';
import VideoTimelineReportPage from './pages/VideoTimelineReportPage';

const NAV_LINK_SX = {
  textDecoration: 'none',
  color: '#8a8895',
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: '0.72rem',
  letterSpacing: '0.06em',
  textTransform: 'uppercase' as const,
  '&:hover': { color: '#e8e6e3' }
} as const;

function AppHeader({ userEmail, onSignOut }: { userEmail?: string; onSignOut?: () => void }) {
  return (
    <Box
      component="header"
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 1100,
        bgcolor: '#08080a',
        borderBottom: '1px solid #26262f',
        px: 3,
        py: 1.25,
        display: 'flex',
        alignItems: 'center',
        gap: 1.25
      }}
    >
      <Box
        component={Link}
        to="/"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.25,
          textDecoration: 'none',
          color: 'inherit'
        }}
      >
        <Box
          sx={{
            width: 26,
            height: 26,
            bgcolor: '#c8f031',
            borderRadius: '5px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: '"JetBrains Mono", monospace',
            fontWeight: 700,
            fontSize: 14,
            color: '#08080a',
            flexShrink: 0
          }}
        >
          α
        </Box>
        <Typography
          sx={{
            fontFamily: '"DM Sans", sans-serif',
            fontWeight: 700,
            fontSize: '0.95rem',
            letterSpacing: '-0.02em',
            color: '#e8e6e3'
          }}
        >
          AlphaEngine
        </Typography>
      </Box>
      <Box sx={{ flexGrow: 1 }} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box
          component="a"
          href={import.meta.env.VITE_WATCHLAB_URL ? `${import.meta.env.VITE_WATCHLAB_URL}/upload` : 'https://lab.alpha-engine.ai/upload'}
          target="_blank"
          rel="noopener noreferrer"
          sx={NAV_LINK_SX}
        >
          Upload
        </Box>
        <Box
          component={Link}
          to="/"
          sx={NAV_LINK_SX}
        >
          Catalog
        </Box>
        <Box
          component={Link}
          to="/studies"
          sx={NAV_LINK_SX}
        >
          Studies
        </Box>
        <Box
          component={Link}
          to="/predictor"
          sx={NAV_LINK_SX}
        >
          Predictor
        </Box>
        <Box
          component={Link}
          to="/observability"
          sx={NAV_LINK_SX}
          data-testid="header-observability-link"
        >
          Observability
        </Box>
        {userEmail && (
          <>
            <Typography
              sx={{ color: '#8a8895', fontFamily: '"JetBrains Mono", monospace', fontSize: '0.68rem', ml: 1 }}
            >
              {userEmail}
            </Typography>
            <Button
              size="small"
              onClick={onSignOut}
              sx={{ color: '#8a8895', textTransform: 'none', fontSize: '0.68rem', minWidth: 'auto' }}
            >
              Sign Out
            </Button>
          </>
        )}
      </Box>
    </Box>
  );
}

/**
 * Per-route ErrorBoundary that auto-clears its error state when the user
 * navigates away (resetKey = current pathname). A crash on one page no longer
 * takes down the entire app — the user can still use header nav to reach
 * healthy pages.
 */
function RouteErrorBoundary({ children, label }: { children: ReactNode; label: string }) {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname} label={label}>
      {children}
    </ErrorBoundary>
  );
}

export default function App() {
  const {
    user, loading, signOut, authEnabled,
    showPasswordReset, updatePassword, dismissPasswordReset,
  } = useAuth();
  const [newPassword, setNewPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSaving, setPasswordSaving] = useState(false);

  const handlePasswordUpdate = async () => {
    if (newPassword.length < 6) {
      setPasswordError('Password must be at least 6 characters.');
      return;
    }
    setPasswordSaving(true);
    setPasswordError(null);
    try {
      await updatePassword(newPassword);
      setNewPassword('');
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Failed to update password.');
    } finally {
      setPasswordSaving(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ minHeight: '100vh', bgcolor: '#08080a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <CircularProgress sx={{ color: '#c8f031' }} />
      </Box>
    );
  }

  // When Supabase auth is configured and user is not logged in, show login
  if (authEnabled && !user) {
    return <LoginPage />;
  }

  return (
    <>
      <AppHeader userEmail={user?.email} onSignOut={signOut} />
      <ErrorBoundary label="root">
        <Routes>
          <Route path="/" element={<RouteErrorBoundary label="home"><HomePage /></RouteErrorBoundary>} />
          <Route path="/studies" element={<RouteErrorBoundary label="studies"><StudiesPage /></RouteErrorBoundary>} />
          <Route path="/studies/:studyId" element={<RouteErrorBoundary label="study-detail"><StudyDetailPage /></RouteErrorBoundary>} />
          <Route path="/observability" element={<RouteErrorBoundary label="observability"><ObservabilityPage /></RouteErrorBoundary>} />
          <Route path="/predictor" element={<RouteErrorBoundary label="predictor"><PredictorPage /></RouteErrorBoundary>} />
          <Route path="/videos/:videoId" element={<RouteErrorBoundary label="video-dashboard"><VideoDashboardPage /></RouteErrorBoundary>} />
          <Route path="/videos/:videoId/timeline-report" element={<RouteErrorBoundary label="timeline-report"><VideoTimelineReportPage /></RouteErrorBoundary>} />
          <Route path="*" element={<RouteErrorBoundary label="home"><HomePage /></RouteErrorBoundary>} />
        </Routes>
      </ErrorBoundary>

      <Dialog open={showPasswordReset} onClose={dismissPasswordReset}>
        <DialogTitle>Set New Password</DialogTitle>
        <DialogContent sx={{ minWidth: 340 }}>
          {passwordError && <Alert severity="error" sx={{ mb: 2 }}>{passwordError}</Alert>}
          <TextField
            fullWidth
            size="small"
            label="New password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoFocus
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={dismissPasswordReset} disabled={passwordSaving}>Cancel</Button>
          <Button onClick={handlePasswordUpdate} variant="contained" disabled={passwordSaving}>
            {passwordSaving ? 'Saving...' : 'Update Password'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
