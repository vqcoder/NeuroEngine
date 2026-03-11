'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_VIDEO_LIBRARY,
  buildStudyHref,
  isHttpUrl,
  makeVideoLibraryItem,
  readVideoLibrary,
  writeVideoLibrary,
  type VideoLibraryItem
} from '@/lib/videoLibrary';

export default function UploadPage() {
  const [videoUrl, setVideoUrl] = useState('');
  const [title, setTitle] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isResolvingVideoUrl, setIsResolvingVideoUrl] = useState(false);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);
  const [hostingId, setHostingId] = useState<string | null>(null);
  const [items, setItems] = useState<VideoLibraryItem[]>([]);

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

  const hostVideoAsset = async (sourceUrl: string, titleHint: string) => {
    const response = await fetch('/api/video/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: sourceUrl, title: titleHint })
    });
    const body = (await response.json().catch(() => null)) as
      | { videoUrl?: string; alreadyUploaded?: boolean; error?: string }
      | null;
    if (!response.ok) {
      throw new Error(body?.error ?? `Cloud hosting failed (${response.status}).`);
    }
    const hostedUrl = body?.videoUrl?.trim() ?? '';
    if (!hostedUrl || (!isHttpUrl(hostedUrl) && !hostedUrl.startsWith('/'))) {
      throw new Error('Cloud hosting returned an invalid URL.');
    }
    return {
      hostedUrl,
      alreadyUploaded: Boolean(body?.alreadyUploaded)
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

    setIsResolvingVideoUrl(true);
    setError(null);
    try {
      const hosted = await hostVideoAsset(trimmedUrl, title.trim() || 'study-video');
      const existingUrl = items.find((entry) => entry.videoUrl === hosted.hostedUrl);
      if (existingUrl) {
        throw new Error('This video URL is already in your library.');
      }

      const nextItem = makeVideoLibraryItem(
        { title: title.trim(), videoUrl: hosted.hostedUrl, originalUrl: trimmedUrl },
        items
      );
      persistItems([...items, nextItem]);
      setVideoUrl('');
      setTitle('');
      setError(null);
      setNotice(
        hosted.alreadyUploaded
          ? `Added existing hosted asset: ${nextItem.title}`
          : `Added and hosted in cloud: ${nextItem.title}`
      );
    } catch (resolveError) {
      setError(
        resolveError instanceof Error
          ? resolveError.message
          : 'Unable to host this source URL in GitHub.'
      );
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
      const hosted = await hostVideoAsset(sourceUrl, item.title);
      const nextItems = items.map((entry) =>
        entry.id === item.id
          ? { ...entry, videoUrl: hosted.hostedUrl, originalUrl: sourceUrl }
          : entry
      );
      persistItems(nextItems);
      setNotice(
        hosted.alreadyUploaded
          ? `Already hosted: ${item.title}`
          : `Hosted in cloud: ${item.title}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cloud hosting failed.');
    } finally {
      setHostingId(null);
    }
  };

  const onRefreshVideoUrl = async (item: VideoLibraryItem) => {
    const sourceUrl = item.originalUrl || item.videoUrl;
    if (!isHttpUrl(sourceUrl)) {
      return;
    }
    setRefreshingId(item.id);
    setError(null);
    try {
      const hosted = await hostVideoAsset(sourceUrl, item.title);
      const nextItems = items.map((entry) =>
        entry.id === item.id
          ? { ...entry, videoUrl: hosted.hostedUrl, originalUrl: sourceUrl }
          : entry
      );
      persistItems(nextItems);
      setNotice(hosted.alreadyUploaded ? `Already hosted: ${item.title}` : `Re-hosted: ${item.title}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed.');
    } finally {
      setRefreshingId(null);
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

            {error ? <p className="status-bad">{error}</p> : null}
            {notice ? (
              <p className="status-good" data-testid="upload-add-notice">
                {notice}
              </p>
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
