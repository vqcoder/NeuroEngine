// ---------------------------------------------------------------------------
// Pure helper functions extracted from study-client.tsx (A21)
// ---------------------------------------------------------------------------

import {
  DEFAULT_VIDEO_LIBRARY,
  WATCHLAB_LIBRARY_ID,
  isHttpUrl,
  readVideoLibrary,
  resolveLibraryStudy,
  type VideoLibraryItem
} from '@/lib/videoLibrary';

import type { BrowserMetadata } from '@/lib/schema';

// ── Storage keys ──────────────────────────────────────────────────────────

const SEEN_STUDIES_KEY = 'watchlab.seenStudies.v1';
const PARTICIPANT_INFO_KEY = 'watchlab.participantInfo.v1';

// ── Participant storage ───────────────────────────────────────────────────

export function saveParticipantInfo(storage: Storage | null, name: string, email: string): void {
  if (!storage) return;
  try {
    storage.setItem(PARTICIPANT_INFO_KEY, JSON.stringify({ name, email }));
  } catch {
    // ignore storage errors
  }
}

export function readParticipantInfo(storage: Storage | null): { name: string; email: string } | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(PARTICIPANT_INFO_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (
      parsed &&
      typeof parsed === 'object' &&
      'name' in parsed &&
      'email' in parsed &&
      typeof (parsed as { name: unknown }).name === 'string' &&
      typeof (parsed as { email: unknown }).email === 'string'
    ) {
      return { name: (parsed as { name: string }).name, email: (parsed as { email: string }).email };
    }
    return null;
  } catch {
    return null;
  }
}

export function readSeenStudyIds(storage: Storage | null): Set<string> {
  if (!storage) return new Set();
  try {
    const raw = storage.getItem(SEEN_STUDIES_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? new Set(parsed as string[]) : new Set();
  } catch {
    return new Set();
  }
}

export function markStudySeen(storage: Storage | null, studyId: string): void {
  if (!storage) return;
  try {
    const seen = readSeenStudyIds(storage);
    seen.add(studyId);
    storage.setItem(SEEN_STUDIES_KEY, JSON.stringify([...seen]));
  } catch {
    // ignore storage errors
  }
}

export function pickUnseenVideo(
  storage: Storage | null,
  currentStudyId: string
): { item: VideoLibraryItem; index: number } | null {
  const items = readVideoLibrary(storage);
  const seen = readSeenStudyIds(storage);
  const candidates = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.studyId !== currentStudyId && !seen.has(item.studyId));
  if (candidates.length === 0) return null;
  return candidates[Math.floor(Math.random() * candidates.length)];
}

// ── UUID / parsing helpers ────────────────────────────────────────────────

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const safeUuid = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return '00000000-0000-4000-8000-000000000000';
};

export const maybeUuid = (value: string | null | undefined): string | undefined => {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return UUID_PATTERN.test(trimmed) ? trimmed : undefined;
};

export const parseSurveyScore = (value: string): number | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 5) {
    return null;
  }
  return parsed;
};

export const parseSequenceIndex = (value: string | null): number | null => {
  if (value === null) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
};

export const parseEntryId = (value: string | null): string | null => {
  if (value === null) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

// ── Formatting helpers ────────────────────────────────────────────────────

import type { StudyStage } from '@/lib/studyTypes';

export const isPlaybackTelemetryStage = (stage: StudyStage) => stage === 'watch' || stage === 'annotation';

export const formatMoment = (value: number) => {
  const totalSeconds = Math.round(value / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')} (${value} ms)`;
};

export const collectBrowserMetadata = (): BrowserMetadata => ({
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  language: navigator.language,
  viewport: {
    width: window.innerWidth,
    height: window.innerHeight
  },
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  hardwareConcurrency: navigator.hardwareConcurrency ?? 0
});

// ── Video URL helpers ─────────────────────────────────────────────────────

export const directVideoExtensionPattern = /\.(mp4|webm|ogg|m4v|mov|m3u8)(?:[?#].*)?$/i;
export const hlsVideoPattern = /\.m3u8(?:[?#].*)?$/i;
export const VIDEO_ASSET_PROXY_PATH = '/api/video-assets/';
export const VIDEO_HLS_PROXY_PATH = '/api/video/hls-proxy';
export const VIDEO_ASSET_FILENAME_PATTERN = /^[\w-]+\.(mp4|webm|mov|m4v)$/i;
export const LEGACY_VIDEO_ASSET_ORIGIN = 'https://biograph-api-production.up.railway.app';

export const looksLikeWebPageUrl = (value: string): boolean => {
  if (!value.startsWith('http://') && !value.startsWith('https://')) {
    return false;
  }
  return !directVideoExtensionPattern.test(value);
};

export const unwrapHlsProxySourceUrl = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    const parsed = trimmed.startsWith('http://') || trimmed.startsWith('https://')
      ? new URL(trimmed)
      : new URL(trimmed, 'https://watchlab.local');
    if (!parsed.pathname.startsWith(VIDEO_HLS_PROXY_PATH)) {
      return null;
    }
    const proxied = parsed.searchParams.get('url')?.trim() ?? '';
    return proxied.length > 0 ? proxied : null;
  } catch {
    return null;
  }
};

export const looksLikeHlsUrl = (value: string): boolean => {
  const lowered = value.toLowerCase();
  const proxied = unwrapHlsProxySourceUrl(value);
  if (proxied && proxied !== value) {
    return looksLikeHlsUrl(proxied);
  }
  return (
    hlsVideoPattern.test(lowered) ||
    lowered.includes('.m3u8') ||
    /[?&](format|type)=m3u8\b/.test(lowered) ||
    lowered.includes(VIDEO_HLS_PROXY_PATH)
  );
};

export const toHlsProxyUrl = (sourceUrl: string): string => {
  const proxied = unwrapHlsProxySourceUrl(sourceUrl);
  if (proxied || sourceUrl.startsWith(VIDEO_HLS_PROXY_PATH)) {
    return sourceUrl;
  }
  return `${VIDEO_HLS_PROXY_PATH}?url=${encodeURIComponent(sourceUrl)}`;
};

export const getDefaultStudyFallbackUrl = (targetStudyId: string): string | null => {
  const match = DEFAULT_VIDEO_LIBRARY.find((entry) => entry.studyId === targetStudyId);
  return match?.videoUrl ?? null;
};

export const applyCanonicalLibraryParams = (
  studyId: string,
  params: URLSearchParams,
  storage: Storage
) => {
  if (params.get('library') !== WATCHLAB_LIBRARY_ID) {
    return null;
  }

  const items = readVideoLibrary(storage);
  const resolved = resolveLibraryStudy(
    items,
    studyId,
    parseSequenceIndex(params.get('index')),
    parseEntryId(params.get('entry_id'))
  );
  if (!resolved) {
    params.delete('library');
    params.delete('index');
    params.delete('entry_id');
    params.delete('video_url');
    params.delete('original_url');
    params.delete('title');
    params.delete('video_id');
    return null;
  }

  const defaultStudyVideoUrl =
    DEFAULT_VIDEO_LIBRARY.find((entry) => entry.studyId === resolved.item.studyId)?.videoUrl ?? null;
  const loweredResolvedVideoUrl = resolved.item.videoUrl.toLowerCase();
  const shouldPinDefaultStudyVideo =
    Boolean(defaultStudyVideoUrl) &&
    (
      /\.m3u8(?:[?#].*)?$/i.test(loweredResolvedVideoUrl) ||
      loweredResolvedVideoUrl.includes('.m3u8') ||
      /[?&](format|type)=m3u8\b/.test(loweredResolvedVideoUrl)
    );
  const canonicalVideoUrl =
    shouldPinDefaultStudyVideo && defaultStudyVideoUrl
      ? defaultStudyVideoUrl
      : resolved.item.videoUrl;

  params.set('library', WATCHLAB_LIBRARY_ID);
  params.set('index', String(resolved.index));
  params.set('entry_id', resolved.item.id);
  params.set('video_url', canonicalVideoUrl);
  params.set('title', resolved.item.title);
  params.set('video_id', resolved.item.studyId);
  if (shouldPinDefaultStudyVideo) {
    params.delete('original_url');
  } else if (resolved.item.originalUrl || isHttpUrl(canonicalVideoUrl)) {
    params.set('original_url', resolved.item.originalUrl ?? canonicalVideoUrl);
  } else {
    params.delete('original_url');
  }
  if (!shouldPinDefaultStudyVideo) {
    return resolved;
  }
  return {
    ...resolved,
    item: {
      ...resolved.item,
      videoUrl: canonicalVideoUrl,
      originalUrl: resolved.item.originalUrl ?? resolved.item.videoUrl
    }
  };
};

// ── Pure video URL helpers (also used inside the component) ───────────────

export const isCloudHostedVideoUrl = (url: string): boolean => {
  const trimmed = url.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.startsWith(VIDEO_ASSET_PROXY_PATH)) {
    return true;
  }
  try {
    const parsed = new URL(trimmed);
    const host = parsed.hostname.toLowerCase();
    if (
      host.includes('biograph-api') &&
      host.endsWith('.up.railway.app') &&
      parsed.pathname.startsWith('/video-assets/')
    ) {
      return true;
    }
    if (host.endsWith('.supabase.co') || host.endsWith('.supabase.in')) {
      return true;
    }
  } catch {
    return false;
  }
  return false;
};

export const mapToProxyAssetUrl = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  if (trimmed.startsWith(VIDEO_ASSET_PROXY_PATH)) {
    return trimmed;
  }
  try {
    const parsed = new URL(trimmed);
    const host = parsed.hostname.toLowerCase();
    if (host.includes('biograph-api') && host.endsWith('.up.railway.app') && parsed.pathname.startsWith('/video-assets/')) {
      const remainder = parsed.pathname.slice('/video-assets/'.length);
      if (!remainder) {
        return null;
      }
      return `${VIDEO_ASSET_PROXY_PATH}${remainder}`;
    }
    const pathParts = parsed.pathname.split('/').filter(Boolean);
    const filename = decodeURIComponent(pathParts.at(-1) ?? '');
    const hostLooksGithub =
      host === 'github.com' ||
      host.endsWith('githubusercontent.com') ||
      host.includes('objects.githubusercontent.com');
    const isGithubReleaseDownloadPath =
      host === 'github.com' &&
      pathParts.length >= 5 &&
      pathParts[2] === 'releases' &&
      pathParts[3] === 'download';
    if (hostLooksGithub && filename && (isGithubReleaseDownloadPath || host !== 'github.com')) {
      if (VIDEO_ASSET_FILENAME_PATTERN.test(filename)) {
        return `${VIDEO_ASSET_PROXY_PATH}${filename}`;
      }
    }
  } catch {
    return null;
  }
  return null;
};

export const normalizeLegacyAssetUrl = (url: string): string => {
  if (!url.startsWith(VIDEO_ASSET_PROXY_PATH)) {
    return url;
  }
  const remainder = url.slice(VIDEO_ASSET_PROXY_PATH.length);
  return `${LEGACY_VIDEO_ASSET_ORIGIN}/video-assets/${remainder}`;
};
