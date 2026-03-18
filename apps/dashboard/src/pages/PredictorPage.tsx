import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Typography
} from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import EditSimulator from '../components/EditSimulator';
import TimelineTrackLanes from '../components/TimelineTrackLanes';
import { usePredictJob } from '../hooks/usePredictJob';
import type { PredictResponse } from '../types';
import {
  DEFAULT_LAYER_VISIBILITY,
  deriveTimeline,
  derivePredictorTracks,
  derivePredictorKeyMoments,
  deriveTimelineEvents,
  formatSeconds,
  toSeekableSecond,
  type PredictorChartClickState,
  type PredictorLayerVisibility
} from '../utils/predictorTimeline';
import {
  DEFAULT_TIMELINE_TRACK_VISIBILITY,
  type TimelineTrackKey,
  type TimelineTrackVisibility
} from '../utils/timelineReport';
import {
  PredictorInputForm,
  PredictorPlaybackPanel,
  PredictorProgressStepper,
  PredictorReactionChart,
  PredictorTrackSummary
} from './predictor';

const DEFAULT_VIDEO_URL = '';

export default function PredictorPage() {
  const [searchParams] = useSearchParams();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const initialVideoUrl = searchParams.get('video_url')?.trim() || DEFAULT_VIDEO_URL;

  // -- Form state (stays in the page as it coordinates with the hook) --
  const initialTab = searchParams.get('tab') === 'file' ? 'file' : 'url';
  const [inputTab, setInputTab] = useState<'url' | 'file'>(initialTab);
  const [videoUrl, setVideoUrl] = useState(initialVideoUrl);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [layerVisibility, setLayerVisibility] = useState<PredictorLayerVisibility>(DEFAULT_LAYER_VISIBILITY);
  const [trackVisibility, setTrackVisibility] = useState<TimelineTrackVisibility>(DEFAULT_TIMELINE_TRACK_VISIBILITY);
  const [currentSec, setCurrentSec] = useState(0);

  // -- Prediction job hook --
  const job = usePredictJob();

  // Register a callback so the hook can switch the input tab when needed
  // (e.g. platform blocks, YouTube rate-limit guides)
  useEffect(() => {
    job.setRequestInputTabSwitch((tab) => {
      setInputTab(tab);
    });
  }, [job.setRequestInputTabSwitch]);

  const {
    loading,
    slowLoad,
    error,
    uploadGuide,
    jobStatus,
    elapsed,
    predictResponse,
    playbackCandidates,
    playbackCandidateIndex,
    playbackError,
    reportPredictorDiagnostic
  } = job;

  const playbackVideoUrl =
    playbackCandidates[Math.min(playbackCandidateIndex, Math.max(0, playbackCandidates.length - 1))] ??
    null;

  // -- Derived data --
  const timeline = useMemo(
    () => deriveTimeline(predictResponse?.predictions ?? []),
    [predictResponse]
  );

  const predictedDurationSec = timeline.length > 0 ? timeline[timeline.length - 1].tSec : 0;

  const predictorTracks = useMemo(
    () => (timeline.length > 0 ? derivePredictorTracks(timeline, predictedDurationSec) : []),
    [timeline, predictedDurationSec]
  );

  const predictorKeyMoments = useMemo(
    () => (timeline.length > 0 ? derivePredictorKeyMoments(timeline, predictedDurationSec) : []),
    [timeline, predictedDurationSec]
  );

  const timelineEvents = useMemo(
    () => deriveTimelineEvents(timeline),
    [timeline]
  );

  // -- Handlers --
  const handleSubmit = useCallback(
    (event: React.FormEvent) => {
      job.onSubmit(event, inputTab, videoUrl, selectedFile);
    },
    [job.onSubmit, inputTab, videoUrl, selectedFile]
  );

  const toggleLayer = useCallback((key: keyof PredictorLayerVisibility) => {
    setLayerVisibility((current) => ({
      ...current,
      [key]: !current[key]
    }));
  }, []);

  const toggleTrack = useCallback((trackKey: TimelineTrackKey) => {
    setTrackVisibility((current) => ({
      ...current,
      [trackKey]: !current[trackKey]
    }));
  }, []);

  const handleSeek = useCallback((seconds: number) => {
    const bounded = toSeekableSecond(Math.min(seconds, predictedDurationSec || seconds));
    setCurrentSec(bounded);
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.currentTime = bounded;
  }, [predictedDurationSec]);

  const handlePlaybackVideoReady = useCallback(() => {
    job.setPlaybackError(null);
  }, [job.setPlaybackError]);

  const handlePlaybackVideoError = useCallback(() => {
    job.setPlaybackCandidateIndex((currentIndex) => {
      if (currentIndex + 1 < playbackCandidates.length) {
        reportPredictorDiagnostic({
          severity: 'warning',
          eventType: 'predictor_playback_source_fallback',
          errorCode: 'candidate_failed',
          message: 'Playback source candidate failed; advancing to fallback candidate.',
          context: {
            failed_candidate_index: currentIndex,
            failed_candidate_url: playbackCandidates[currentIndex] ?? null,
            next_candidate_url: playbackCandidates[currentIndex + 1] ?? null
          }
        });
        return currentIndex + 1;
      }
      const finalMessage = 'Playback preview failed for all available source URLs.';
      job.setPlaybackError(finalMessage);
      reportPredictorDiagnostic({
        severity: 'error',
        eventType: 'predictor_playback_failed',
        errorCode: 'all_candidates_failed',
        message: finalMessage,
        context: {
          playback_candidates: playbackCandidates
        }
      });
      return currentIndex;
    });
  }, [playbackCandidates, reportPredictorDiagnostic, job.setPlaybackCandidateIndex, job.setPlaybackError]);

  const handleChartClick = useCallback((state: PredictorChartClickState) => {
    const activeLabel = state.activeLabel;
    if (activeLabel === undefined || activeLabel === null) {
      return;
    }
    const candidate = typeof activeLabel === 'number' ? activeLabel : Number(activeLabel);
    if (!Number.isFinite(candidate)) {
      return;
    }
    handleSeek(candidate);
  }, [handleSeek]);

  const handleClearError = useCallback(() => {
    // When switching tabs, also clear the upload guide
    job.setUploadGuide(null);
  }, [job.setUploadGuide]);

  const handleInputTabChange = useCallback((tab: 'url' | 'file') => {
    setInputTab(tab);
  }, []);

  // -- Render --
  const hasResults = predictResponse !== null;
  const hasTimeline = hasResults && timeline.length > 0;

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1200, mx: 'auto' }}>
      <Stack spacing={2.5}>
        {/* Input card */}
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="h4" fontWeight={700}>
                Predictor Lab
              </Typography>
              <Typography color="text.secondary">
                Upload a video file or paste a URL to predict reaction traces before running a live viewer study.
              </Typography>

              <PredictorInputForm
                inputTab={inputTab}
                onInputTabChange={handleInputTabChange}
                videoUrl={videoUrl}
                onVideoUrlChange={setVideoUrl}
                selectedFile={selectedFile}
                onSelectedFileChange={setSelectedFile}
                loading={loading}
                onSubmit={handleSubmit}
                onClearError={handleClearError}
              />

              {loading ? (
                <PredictorProgressStepper
                  inputTab={inputTab}
                  jobStatus={jobStatus}
                  elapsed={elapsed}
                  slowLoad={slowLoad}
                  onCancel={job.handleCancel}
                />
              ) : null}

              {uploadGuide ? (
                <Alert
                  severity="warning"
                  onClose={() => job.setUploadGuide(null)}
                  data-testid="predictor-upload-guide"
                >
                  {uploadGuide}
                </Alert>
              ) : null}

              {error ? <Alert severity="error">{error}</Alert> : null}

              <Alert severity="info" data-testid="predictor-disclaimer">
                Predictions use the biograph API inference backend and return readout-aligned proxy channels
                (attention, reward proxy, velocity, valence, arousal, novelty, blink, tracking confidence).
                Webcam-specific AU/gaze traces still require live session capture.
              </Alert>
            </Stack>
          </CardContent>
        </Card>

        {/* Output metadata */}
        {hasResults ? (
          <PredictionOutputCard
            predictResponse={predictResponse}
            timeline={timeline}
            predictedDurationSec={predictedDurationSec}
            currentSec={currentSec}
          />
        ) : null}

        {/* Playback + key events */}
        {hasTimeline ? (
          <Card>
            <CardContent>
              <PredictorPlaybackPanel
                videoRef={videoRef}
                playbackVideoUrl={playbackVideoUrl}
                playbackError={playbackError}
                timelineEvents={timelineEvents}
                onTimeUpdate={setCurrentSec}
                onVideoReady={handlePlaybackVideoReady}
                onVideoError={handlePlaybackVideoError}
                onSeek={handleSeek}
              />
            </CardContent>
          </Card>
        ) : null}

        {/* Reaction chart */}
        {hasTimeline ? (
          <Card>
            <CardContent>
              <PredictorReactionChart
                timeline={timeline}
                layerVisibility={layerVisibility}
                currentSec={currentSec}
                onToggleLayer={toggleLayer}
                onChartClick={handleChartClick}
              />
            </CardContent>
          </Card>
        ) : null}

        {/* Track lanes */}
        {hasTimeline ? (
          <TimelineTrackLanes
            durationMs={Math.round(predictedDurationSec * 1000)}
            scenes={[]}
            cuts={[]}
            tracks={predictorTracks}
            visibility={trackVisibility}
            onToggleTrack={toggleTrack}
            onSeek={handleSeek}
            keyMoments={predictorKeyMoments}
          />
        ) : null}

        {/* Track evidence summary */}
        {hasTimeline ? (
          <PredictorTrackSummary tracks={predictorTracks} />
        ) : null}

        {/* Edit simulator */}
        {hasTimeline ? (
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={700} mb={2}>
                Edit Simulator
              </Typography>
              <EditSimulator trace={timeline} />
            </CardContent>
          </Card>
        ) : null}
      </Stack>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Small inline sub-component for the prediction output metadata card
// ---------------------------------------------------------------------------

function PredictionOutputCard({
  predictResponse,
  timeline,
  predictedDurationSec,
  currentSec
}: {
  predictResponse: PredictResponse;
  timeline: { length: number };
  predictedDurationSec: number;
  currentSec: number;
}) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="h6" fontWeight={700}>
            Prediction output
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip label={`Model ${predictResponse.model_artifact}`} />
            <Chip label={`Backend ${predictResponse.prediction_backend}`} />
            <Chip label={`Points ${timeline.length}`} />
            <Chip label={`Duration ${predictedDurationSec.toFixed(1)}s`} />
            <Chip label={`Current ${formatSeconds(currentSec)}`} data-testid="predictor-current-time" />
          </Stack>
          {predictResponse.video_id ? (
            <Alert
              severity="success"
              data-testid="predictor-catalog-saved"
              action={
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    variant="contained"
                    color="success"
                    href={`/videos/${predictResponse.video_id}/timeline-report`}
                    data-testid="predictor-open-timeline"
                  >
                    Open Timeline Report
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    color="success"
                    href={`/videos/${predictResponse.video_id}`}
                    data-testid="predictor-open-report"
                  >
                    Deep Dive
                  </Button>
                </Stack>
              }
            >
              Video saved to catalog.
            </Alert>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}
