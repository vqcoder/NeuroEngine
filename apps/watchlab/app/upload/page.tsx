'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  { key: 'downloading', label: 'Downloading' },
  { key: 'uploading', label: 'Uploading' },
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
            {step === 'queued' && 'Starting download…'}
            {step === 'downloading' && `Downloading video… (${elapsedSec}s)`}
            {step === 'uploading' && `Uploading to cloud… (${elapsedSec}s)`}
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
  const [isResolvingVideoUrl, setIsResolvingVideoUrl] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [hostingId, setHostingId] = useState<string | null>(null);
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

  useEffect(() => {
    setItems(readVideoLibrary(typeof window !== 'undefined' ? window.localStorage : null));
  }, []);

  const totalLabel = useMemo(() => {
    if (items.length === 0) {
      return 'No videos saved yet.';
    }
    if (items.length === 1) {
      return '1 video saved.';
    }
    return `${items.length} videos saved.`;
  }, [items.length]);

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

  const onAddVideo = async (event: React.FormEvent<HTMLFormElement>) => {
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
    setIsResolvingVideoUrl(true);
    setError(null);
    setUploadError(undefined);
    setInviteUrl(null);
    setCopied(false);
    setUploadStep('queued');
    startProgressTimer();

    // Advance to "downloading" after a brief moment
    const advanceTimer = setTimeout(() => setUploadStep('downloading'), 800);

    // Advance to "uploading" after a few seconds
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
      setIsResolvingVideoUrl(false);
    }
  };

  const onRemoveVideo = (id: string) => {
    const nextItems = items.filter((item) => item.id !== id);
    persistItems(nextItems);
  };

  const onClearLibrary = () => {
    persistItems([]);
  };

  const onResetToDefaults = () => {
    persistItems(DEFAULT_VIDEO_LIBRARY);
    setNotice('Library reset to default videos.');
  };

  const onHostInCloud = async (item: VideoLibraryItem) => {
    const sourceUrl = item.originalUrl || item.videoUrl;
    if (!isHttpUrl(sourceUrl)) return;
    setHostingId(item.id);
    setError(null);
    try {
      const result = await createStudy(sourceUrl, item.title);
      setNotice(`Study created: ${item.title}`);
      setInviteUrl(result.inviteUrl);
      setCopied(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Study creation failed.');
    } finally {
      setHostingId(null);
    }
  };

  const onRefreshVideoUrl = async (item: VideoLibraryItem) => {
    const sourceUrl = item.originalUrl || item.videoUrl;
    if (!isHttpUrl(sourceUrl)) return;
    setRefreshingId(item.id);
    setError(null);
    try {
      const result = await createStudy(sourceUrl, item.title);
      setNotice(`Study created: ${item.title}`);
      setInviteUrl(result.inviteUrl);
      setCopied(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed.');
    } finally {
      setRefreshingId(null);
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
          <h1>Video Library Upload</h1>
          <p>
            Add study videos once, then run participants through the sequence with one click.
            When a video ends, WatchLab can launch the next study directly.
          </p>
          <p className="muted">{totalLabel}</p>

          <form className="stack" onSubmit={onAddVideo}>
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
                disabled={isResolvingVideoUrl}
              >
                {isResolvingVideoUrl ? 'Hosting in cloud...' : 'Add to library'}
              </button>
              {items.length > 0 ? (
                <Link href={buildStudyHref(items[0], 0)} className="button-link" data-testid="start-sequence-link">
                  Start sequence (video 1)
                </Link>
              ) : null}
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

        <section className="panel stack" data-testid="library-list-panel">
          <h2>Saved Study Sequence</h2>
          {items.length === 0 ? (
            <p className="muted">
              No entries yet. Add at least one URL above to build a click-through sequence.
            </p>
          ) : (
            <div className="stack">
              {items.map((item, index) => (
                <div key={item.id} className="panel stack" style={{ padding: '16px' }} data-testid="library-item">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <strong>
                      {index + 1}. {item.title}
                    </strong>
                    <small>Study ID: {item.studyId}</small>
                  </div>
                  <small style={{ wordBreak: 'break-all' }}>{item.videoUrl}</small>
                  <div className="row">
                    <Link href={buildStudyHref(item, index)} className="button-link" data-testid="start-item-link">
                      Start this study
                    </Link>
                    {isHttpUrl(item.originalUrl ?? item.videoUrl) ? (
                      <button
                        onClick={() => void onRefreshVideoUrl(item)}
                        disabled={refreshingId === item.id || hostingId === item.id}
                        data-testid="refresh-item-button"
                      >
                        {refreshingId === item.id ? 'Re-hosting...' : 'Re-host in cloud'}
                      </button>
                    ) : null}
                    <button
                      onClick={() => void onHostInCloud(item)}
                      disabled={hostingId === item.id || refreshingId === item.id}
                      data-testid="host-cloud-button"
                    >
                      {hostingId === item.id ? 'Uploading...' : 'Host in cloud'}
                    </button>
                    <button onClick={() => onRemoveVideo(item.id)} data-testid="remove-item-button">
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="row">
            <button onClick={onResetToDefaults} data-testid="reset-library-button">
              Reset to defaults
            </button>
            {items.length > 0 ? (
              <button onClick={onClearLibrary} data-testid="clear-library-button">
                Clear library
              </button>
            ) : null}
          </div>
        </section>
      </div>
    </main>
  );
}
