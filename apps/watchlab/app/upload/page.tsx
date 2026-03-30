'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { isHttpUrl } from '@/lib/videoLibrary';

type UploadStep = 'idle' | 'queued' | 'downloading' | 'uploading' | 'complete' | 'error';

const UPLOAD_STEPS: { key: Exclude<UploadStep, 'idle'>; label: string }[] = [
  { key: 'queued', label: 'Queued' },
  { key: 'downloading', label: 'Creating study' },
  { key: 'uploading', label: 'Registering video' },
  { key: 'complete', label: 'Complete' }
];

function UploadProgress({ step, elapsedSec, errorMessage }: { step: UploadStep; elapsedSec: number; errorMessage?: string }) {
  if (step === 'idle') return null;

  const activeIndex = step === 'error'
    ? -1
    : UPLOAD_STEPS.findIndex((s) => s.key === step);

  return (
    <div className="upload-progress" data-testid="upload-progress">
      <div className="upload-steps-row">
        {UPLOAD_STEPS.map((s, i) => {
          const isDone = activeIndex > i;
          const isActive = activeIndex === i && step !== 'error';
          const isError = step === 'error';
          return (
            <div key={s.key} className="upload-step-item">
              <div
                className={[
                  'upload-step-circle',
                  isDone ? 'done' : '',
                  isActive ? 'active' : '',
                  isError ? 'error' : ''
                ].filter(Boolean).join(' ')}
              >
                {isDone ? '✓' : i + 1}
              </div>
              {i < UPLOAD_STEPS.length - 1 && (
                <div className={`upload-step-line ${isDone ? 'done' : ''}`} />
              )}
              <span
                className={[
                  'upload-step-label',
                  isActive ? 'active' : '',
                  isDone ? 'done' : ''
                ].filter(Boolean).join(' ')}
              >
                {s.label}
              </span>
            </div>
          );
        })}
      </div>
      <p className="upload-progress-status">
        {step === 'error' ? (
          <span className="status-bad">{errorMessage ?? 'Upload failed'}</span>
        ) : step === 'complete' ? (
          <span className="status-good">Done!</span>
        ) : (
          <>
            {step === 'queued' && 'Starting…'}
            {step === 'downloading' && `Creating study… (${elapsedSec}s)`}
            {step === 'uploading' && `Registering video… (${elapsedSec}s)`}
          </>
        )}
      </p>
    </div>
  );
}

export default function UploadPage() {
  const [videoUrl, setVideoUrl] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // --- Upload progress bar state ---
  const [uploadStep, setUploadStep] = useState<UploadStep>('idle');
  const [uploadElapsed, setUploadElapsed] = useState(0);
  const [uploadError, setUploadError] = useState<string | undefined>();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  const startProgressTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    setUploadElapsed(0);
    timerRef.current = setInterval(() => {
      setUploadElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 500);
  }, []);

  const stopProgressTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopProgressTimer();
  }, [stopProgressTimer]);

  // Clear stale localStorage video library cache from the old UI
  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('watchlab.videoLibrary.v1');
    }
  }, []);

  const createStudy = async (sourceUrl: string, titleHint: string) => {
    const response = await fetch('/api/video/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: sourceUrl, title: titleHint })
    });
    const body = (await response.json().catch(() => null)) as
      | { success?: boolean; studyId?: string; videoId?: string; inviteUrl?: string; error?: string }
      | null;
    if (!response.ok) {
      throw new Error(body?.error ?? `Study creation failed (${response.status}).`);
    }
    if (!body?.studyId || !body?.inviteUrl) {
      throw new Error('Study creation returned an incomplete response.');
    }
    return {
      studyId: body.studyId,
      videoId: body.videoId!,
      inviteUrl: body.inviteUrl,
    };
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedUrl = videoUrl.trim();
    setNotice(null);
    if (trimmedUrl.length === 0) {
      setError('Enter a video URL first.');
      return;
    }
    if (!isHttpUrl(trimmedUrl)) {
      setError('Video URL must be a valid http(s) link.');
      return;
    }

    // --- Start progress bar ---
    setIsSubmitting(true);
    setError(null);
    setUploadError(undefined);
    setInviteUrl(null);
    setCopied(false);
    setUploadStep('queued');
    startProgressTimer();

    // Advance to "creating study" after a brief moment
    const advanceTimer = setTimeout(() => setUploadStep('downloading'), 800);

    // Advance to "registering video" after a few seconds
    const uploadTimer = setTimeout(() => setUploadStep('uploading'), 3_000);

    try {
      const result = await createStudy(trimmedUrl, title.trim() || 'study-video');

      clearTimeout(advanceTimer);
      clearTimeout(uploadTimer);

      setUploadStep('complete');
      stopProgressTimer();

      setVideoUrl('');
      setTitle('');
      setError(null);
      setInviteUrl(result.inviteUrl);
      setNotice('Study created successfully.');

      // Auto-hide progress bar after a few seconds
      setTimeout(() => setUploadStep('idle'), 4000);
    } catch (resolveError) {
      clearTimeout(advanceTimer);
      clearTimeout(uploadTimer);
      stopProgressTimer();
      const msg = resolveError instanceof Error
        ? resolveError.message
        : 'Unable to create study.';
      setUploadStep('error');
      setUploadError(msg);
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const onCopyInviteUrl = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select the input text
    }
  };

  return (
    <main>
      <div className="stack" style={{ maxWidth: 980, margin: '0 auto' }}>
        <section className="panel stack" data-testid="upload-page">
          <h1>Create Study</h1>
          <p>
            Add a video URL to create a new study. Share the invite link with participants.
          </p>

          <form className="stack" onSubmit={onSubmit}>
            <label htmlFor="video-title">Study title (optional)</label>
            <input
              id="video-title"
              type="text"
              placeholder="Example: Brand Film A"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                if (error) {
                  setError(null);
                }
              }}
              data-testid="upload-title-input"
            />

            <label htmlFor="video-url">Video URL</label>
            <input
              id="video-url"
              type="text"
              placeholder="https://cdn.example.com/video.mp4"
              value={videoUrl}
              onChange={(event) => {
                setVideoUrl(event.target.value);
                if (error) {
                  setError(null);
                }
              }}
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              data-testid="upload-video-url-input"
              required
            />

            <div className="row">
              <button
                type="submit"
                className="primary"
                data-testid="add-video-button"
                disabled={isSubmitting}
              >
                {isSubmitting ? 'Creating study...' : 'Create study'}
              </button>
              <Link href="/" className="button-link" data-testid="back-home-link">
                Back home
              </Link>
            </div>

            <UploadProgress step={uploadStep} elapsedSec={uploadElapsed} errorMessage={uploadError} />

            {error && uploadStep !== 'error' ? <p className="status-bad">{error}</p> : null}
            {notice ? (
              <p className="status-good" data-testid="upload-add-notice">
                {notice}
              </p>
            ) : null}

            {inviteUrl ? (
              <div
                data-testid="invite-url-panel"
                style={{
                  background: '#111116',
                  border: '1px solid #26262f',
                  borderRadius: 8,
                  padding: '12px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <input
                  type="text"
                  readOnly
                  value={inviteUrl}
                  data-testid="invite-url-input"
                  style={{
                    flex: 1,
                    background: 'transparent',
                    border: 'none',
                    color: '#e0e0e0',
                    fontFamily: 'monospace',
                    fontSize: 14,
                    outline: 'none',
                  }}
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  onClick={() => void onCopyInviteUrl()}
                  data-testid="copy-invite-url-button"
                  style={{
                    background: '#c8f031',
                    color: '#111116',
                    border: 'none',
                    borderRadius: 6,
                    padding: '6px 14px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {copied ? 'Copied!' : 'Copy link'}
                </button>
              </div>
            ) : null}
          </form>
        </section>
      </div>
    </main>
  );
}
