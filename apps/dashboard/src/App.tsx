import type { ReactNode } from 'react';
import { Route, Routes, Link, useLocation } from 'react-router-dom';
import { Box, Typography } from '@mui/material';
import ErrorBoundary from './components/ErrorBoundary';
import HomePage from './pages/HomePage';
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

function AppHeader() {
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
  return (
    <>
      <AppHeader />
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
    </>
  );
}
