'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  DEFAULT_VIDEO_LIBRARY,
  buildStudyHref,
  isHttpUrl,
  makeVideoLibraryItem,
  readVideoLibrary,
  writeVideoLibrary,
  type VideoLibraryItem
} from '@/lib/videoLibrary';

type UploadStep = 'idle' | 'queued' | 'downloading' | 'uploading' | 'complete' | 'error';

const UPLOAD_STEPS: { key: Exclude<UploadStep, 'idle'>; label: string }[] = [
  { key: 'queued', label: 'Queued' },
  { key: 'downloading', label: 'Creating study' },
  { key: 'uploading', label: 'Registering video' },
  { key: 'complete', label: 'Complete' }
];

const cardStyle: React.CSSProperties = {
  background: '#111116',
  border: '1px solid #26262f',
  borderRadius: 8,
  padding: '14px 16px',
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const btnBase: React.CSSProperties = {
  fontFamily: 'monospace',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  padding: '5px 12px',
  borderRadius: 5,
  border: '1px solid #26262f',
  background: 'transparent',
  color: '#e8e6e3',
  cursor: 'pointer',
};

function truncateUrl(url: string, max = 60): string {
  if (url.length <= max) return url;
  return url.slice(0, max - 1) + '…';
}

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
  const router = useRouter();
  const [videoUrl, setVideoUrl] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [items, setItems] = useState<VideoLibraryItem[]>([]);

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

  // Load video library from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setItems(readVideoLibrary(window.localStorage));
    }
  }, []);

  const persistItems = (nextItems: VideoLibraryItem[]) => {
    setItems(nextItems);
    writeVideoLibrary(typeof window !== 'undefined' ? window.localStorage : null, nextItems);
  };

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

      const nextItem = makeVideoLibraryItem(
        { title: title.trim(), videoUrl: trimmedUrl, originalUrl: trimmedUrl },
        items
      );
      persistItems([...items, nextItem]);

      setVideoUrl('');
      setTitle('');
      setError(null);
      setInviteUrl(result.inviteUrl);
      setNotice(`Study created: ${nextItem.title}`);

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

  const onRemoveItem = (id: string) => {
    persistItems(items.filter((item) => item.id !== id));
  };

  const onResetToDefaults = () => {
    persistItems(DEFAULT_VIDEO_LIBRARY);
  };

  const onClearLibrary = () => {
    persistItems([]);
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

        {/* ── Saved Study Sequence ── */}
        <section className="panel stack" data-testid="video-library-section">
          <h2>Saved Study Sequence</h2>
          <p style={{ color: '#8a8895', fontSize: 14 }}>
            {items.length === 0
              ? 'No videos saved yet.'
              : items.length === 1
                ? '1 video saved.'
                : `${items.length} videos saved.`}
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map((item, idx) => (
              <div key={item.id} style={cardStyle} data-testid={`library-card-${item.id}`}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                    <span style={{ color: '#5a585c', fontFamily: 'monospace', fontSize: 13, fontWeight: 600 }}>
                      {idx + 1}.
                    </span>
                    <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>
                      {item.title}
                    </span>
                  </div>
                  <span style={{ color: '#5a585c', fontFamily: 'monospace', fontSize: 12, flexShrink: 0 }}>
                    {item.studyId}
                  </span>
                </div>

                <span style={{ color: '#8a8895', fontSize: 12, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                  {truncateUrl(item.videoUrl)}
                </span>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 2 }}>
                  <button
                    type="button"
                    style={btnBase}
                    data-testid={`start-study-${item.studyId}`}
                    onClick={() => router.push(buildStudyHref(item, idx))}
                    onMouseEnter={(e) => { e.currentTarget.style.color = '#c8f031'; e.currentTarget.style.borderColor = '#c8f031'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = '#e8e6e3'; e.currentTarget.style.borderColor = '#26262f'; }}
                  >
                    START THIS STUDY
                  </button>
                  <button type="button" style={{ ...btnBase, opacity: 0.4, cursor: 'not-allowed' }} disabled title="Coming soon">
                    RE-HOST IN CLOUD
                  </button>
                  <button type="button" style={{ ...btnBase, opacity: 0.4, cursor: 'not-allowed' }} disabled title="Coming soon">
                    HOST IN CLOUD
                  </button>
                  <button
                    type="button"
                    style={btnBase}
                    data-testid={`remove-${item.id}`}
                    onClick={() => onRemoveItem(item.id)}
                    onMouseEnter={(e) => { e.currentTarget.style.color = '#f05050'; e.currentTarget.style.borderColor = '#f05050'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = '#e8e6e3'; e.currentTarget.style.borderColor = '#26262f'; }}
                  >
                    REMOVE
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              style={btnBase}
              data-testid="reset-to-defaults"
              onClick={onResetToDefaults}
            >
              RESET TO DEFAULTS
            </button>
            <button
              type="button"
              style={btnBase}
              data-testid="clear-library"
              onClick={onClearLibrary}
            >
              CLEAR LIBRARY
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
