'use client';

import type { RefObject } from 'react';
import type { QualityState, WebcamStatus } from '@/lib/studyTypes';

export interface StudyCameraCheckProps {
  webcamVideoRef: RefObject<HTMLVideoElement | null>;
  qualityCanvasRef: RefObject<HTMLCanvasElement | null>;
  captureCanvasRef: RefObject<HTMLCanvasElement | null>;
  quality: QualityState;
  webcamStatus: WebcamStatus;
  webcamBypassed: boolean;
  audioCheckPlayed: boolean;
  audioConfirmed: boolean;
  canAdvanceFromCamera: boolean;
  requireWebcam: boolean;
  onRetryWebcam: () => void;
  onContinueWithoutWebcam: () => void;
  playAudioCheckTone: () => void;
  setAudioConfirmed: (value: boolean) => void;
  onStartStudyVideo: () => void;
}

export default function StudyCameraCheck({
  webcamVideoRef,
  qualityCanvasRef,
  captureCanvasRef,
  quality,
  webcamStatus,
  webcamBypassed,
  audioCheckPlayed,
  audioConfirmed,
  canAdvanceFromCamera,
  requireWebcam,
  onRetryWebcam,
  onContinueWithoutWebcam,
  playAudioCheckTone,
  setAudioConfirmed,
  onStartStudyVideo
}: StudyCameraCheckProps) {
  const lightCheck = quality.brightnessOk
    ? 'check-pass'
    : quality.qualityFlags.includes('low_light')
      ? 'check-fail'
      : 'check-idle';
  const faceCheck = quality.faceOk
    ? 'check-pass'
    : quality.qualityFlags.includes('face_lost')
      ? 'check-fail'
      : 'check-idle';
  const fpsCheck = quality.fpsOk ? 'check-pass' : webcamStatus === 'granted' ? 'check-warn' : 'check-idle';
  const audioCheck = audioConfirmed ? 'check-pass' : 'check-idle';
  const badgeClass = quality.pass ? 'badge-pass' : webcamStatus === 'granted' ? 'badge-checking' : 'badge-waiting';
  const badgeLabel = quality.pass ? '\u25cf QUALITY PASS' : webcamStatus === 'granted' ? '\u25cf Checking...' : '\u25cf Waiting for camera';

  return (
    <main className="camera-stage-full">
      <canvas ref={qualityCanvasRef} style={{ display: 'none' }} />
      <canvas ref={captureCanvasRef} style={{ display: 'none' }} />
      <div className="camera-layout">
        <div className="camera-preview-col">
          <div className="camera-preview-wrap">
            <video
              ref={webcamVideoRef}
              width={224}
              height={168}
              muted
              autoPlay
              playsInline
              className="camera-webcam-large"
              data-testid="webcam-preview"
            />
            <div className={`camera-quality-badge ${badgeClass}`}>{badgeLabel}</div>
          </div>
        </div>

        <div className="camera-setup-col">
          <div className="camera-setup-header">
            <div className="camera-setup-step">Step 2 of 3</div>
            <h2>Camera Setup</h2>
            <p>Before we start, confirm your setup is good. All checks must pass to continue.</p>
          </div>

          <div className="camera-checklist">
            <div className={`camera-check-item ${lightCheck}`}>
              <div className="camera-check-dot" />
              <div className="camera-check-content">
                <span className="camera-check-label">Lighting</span>
                <span className="camera-check-status">
                  {quality.brightnessOk
                    ? 'Good \u2014 clear front lighting'
                    : quality.qualityFlags.includes('low_light')
                      ? 'Too dark \u2014 add light in front of you'
                      : 'Waiting for camera...'}
                </span>
              </div>
            </div>

            <div className={`camera-check-item ${faceCheck}`}>
              <div className="camera-check-dot" />
              <div className="camera-check-content">
                <span className="camera-check-label">Face visible</span>
                <span className="camera-check-status">
                  {quality.faceOk
                    ? 'Centered and clear'
                    : quality.qualityFlags.includes('face_lost')
                      ? 'Move closer and center your face in frame'
                      : 'Waiting for camera...'}
                </span>
              </div>
            </div>

            <div className={`camera-check-item ${fpsCheck}`}>
              <div className="camera-check-dot" />
              <div className="camera-check-content">
                <span className="camera-check-label">Camera stable</span>
                <span className="camera-check-status">
                  {quality.fpsOk
                    ? `${quality.fps.toFixed(0)} fps \u2014 stable`
                    : webcamStatus === 'granted'
                      ? 'Low FPS \u2014 try closing other apps or tabs'
                      : 'Waiting for camera...'}
                </span>
              </div>
            </div>

            <div className={`camera-check-item ${audioCheck}`}>
              <div className="camera-check-dot" />
              <div className="camera-check-content">
                <span className="camera-check-label">Audio</span>
                <div className="camera-check-audio">
                  <button
                    onClick={playAudioCheckTone}
                    className="camera-audio-btn"
                    data-testid="play-audio-check"
                  >
                    {audioCheckPlayed ? 'Replay test sound' : 'Play test sound'}
                  </button>
                  {audioCheckPlayed && !audioConfirmed ? (
                    <button
                      className="camera-audio-confirm-btn"
                      onClick={() => setAudioConfirmed(true)}
                      data-testid="audio-confirmed-button"
                    >
                      I can hear it
                    </button>
                  ) : null}
                </div>
                {!audioCheckPlayed ? (
                  <span className="camera-check-status" style={{ marginTop: 2 }}>
                    Play the test sound first
                  </span>
                ) : !audioConfirmed ? (
                  <span className="camera-check-status" style={{ marginTop: 2 }}>
                    Unmute your system and browser tab if needed
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <div className="camera-tips">
            <div className="camera-tips-label">For best results</div>
            <div className="camera-tip-row">Face a window or lamp directly &mdash; light in front of you, not behind</div>
            <div className="camera-tip-row">Avoid bright backgrounds (window or lamp directly behind you)</div>
            <div className="camera-tip-row">Remove hats, sunglasses, or anything covering your face</div>
            <div className="camera-tip-row">Sit at arm&#39;s length from the screen, camera at eye level</div>
          </div>

          {webcamStatus === 'denied' ? (
            <p className="status-bad" style={{ fontSize: 13 }}>
              {requireWebcam
                ? 'Camera permission is required. Allow camera access in your browser and retry.'
                : 'Camera permission not granted. You can retry or continue without webcam.'}
            </p>
          ) : null}

          <div className="camera-actions">
            <button onClick={onRetryWebcam} className="camera-retry-btn" data-testid="retry-webcam-button">
              Retry
            </button>
            <button
              className="primary"
              onClick={onStartStudyVideo}
              disabled={!canAdvanceFromCamera}
              data-testid="start-watch-button"
              style={{ flex: 1 }}
            >
              {canAdvanceFromCamera ? 'Start viewing \u2192' : 'Complete setup to continue'}
            </button>
          </div>

          {webcamBypassed ? (
            <p className="status-warn" style={{ fontSize: 12 }} data-testid="webcam-bypassed-note">
              Proceeding without webcam for this session.
            </p>
          ) : null}
          {!requireWebcam ? (
            <button
              onClick={onContinueWithoutWebcam}
              className="camera-skip-btn"
              data-testid="continue-without-webcam-button"
            >
              Skip &mdash; continue without webcam
            </button>
          ) : null}
        </div>
      </div>
    </main>
  );
}
