import { z } from 'zod';

export const VIDEO_LIBRARY_STORAGE_KEY = 'watchlab.videoLibrary.v1';
export const WATCHLAB_LIBRARY_ID = 'watchlab-local';
const directVideoExtensionPattern = /\.(mp4|webm|ogg|m4v|mov|m3u8)(?:[?#].*)?$/i;
const VIDEO_PROXY_PATH = '/api/video-assets';
const VIDEO_ASSET_FILENAME_PATTERN = /^[\w-]+\.(mp4|webm|mov|m4v)$/i;
const hlsVideoPattern = /\.m3u8(?:[?#].*)?$/i;

export type VideoLibraryItem = {
  id: string;
  studyId: string;
  title: string;
  videoUrl: string;
  originalUrl?: string;
  createdAt: string;
};

export type ResolvedVideoLibraryStudy = {
  item: VideoLibraryItem;
  index: number;
};

const videoLibraryItemSchema = z.object({
  id: z.string().min(1),
  studyId: z.string().min(1),
  title: z.string().min(1),
  videoUrl: z.string().min(1),
  originalUrl: z.string().optional(),
  createdAt: z.string().datetime()
});

const videoLibrarySchema = z.array(videoLibraryItemSchema);

const slugify = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);

export const isHttpUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

export const isLikelyDirectVideoUrl = (value: string): boolean => {
  if (value.startsWith('/')) {
    return true;
  }
  return directVideoExtensionPattern.test(value.trim());
};

const looksLikeHlsUrl = (value: string): boolean => {
  const lowered = value.toLowerCase();
  return (
    hlsVideoPattern.test(lowered) ||
    lowered.includes('.m3u8') ||
    /[?&](format|type)=m3u8\b/.test(lowered)
  );
};

const guessTitleFromUrl = (value: string): string => {
  try {
    const parsed = new URL(value);
    const pathPart = parsed.pathname.split('/').filter(Boolean).at(-1);
    if (pathPart) {
      return decodeURIComponent(pathPart).replace(/\.[a-z0-9]+$/i, '');
    }
    return parsed.hostname;
  } catch {
    return value;
  }
};

export const deriveStudyId = (title: string, fallbackSeed?: string) => {
  const slug = slugify(title) || slugify(fallbackSeed ?? '') || 'study';
  return slug;
};

const safeRandom = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.round(Math.random() * 1_000_000)}`;
};

const migrateLegacyVideoAssetUrl = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed || trimmed.startsWith(`${VIDEO_PROXY_PATH}/`)) {
    return trimmed;
  }
  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.toLowerCase();
    if (
      (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      hostname.includes('biograph-api') &&
      hostname.endsWith('.up.railway.app') &&
      parsed.pathname.startsWith('/video-assets/')
    ) {
      const remainder = parsed.pathname.slice('/video-assets/'.length);
      if (!remainder) {
        return trimmed;
      }
      return `${VIDEO_PROXY_PATH}/${remainder}${parsed.search}${parsed.hash}`;
    }
    const rawPathParts = parsed.pathname.split('/').filter(Boolean);
    const filenameCandidate = decodeURIComponent(rawPathParts.at(-1) ?? '');
    const hostLooksGithub =
      hostname === 'github.com' ||
      hostname.endsWith('githubusercontent.com') ||
      hostname.includes('objects.githubusercontent.com');
    const isGithubReleaseDownloadPath =
      hostname === 'github.com' &&
      rawPathParts.length >= 5 &&
      rawPathParts[2] === 'releases' &&
      rawPathParts[3] === 'download';
    if (hostLooksGithub && filenameCandidate && (isGithubReleaseDownloadPath || hostname !== 'github.com')) {
      if (VIDEO_ASSET_FILENAME_PATTERN.test(filenameCandidate)) {
        return `${VIDEO_PROXY_PATH}/${filenameCandidate}`;
      }
    }
  } catch {
    return trimmed;
  }
  return trimmed;
};

export const makeVideoLibraryItem = (
  input: {
    title?: string;
    videoUrl: string;
    originalUrl?: string;
  },
  existingItems: VideoLibraryItem[]
): VideoLibraryItem => {
  const normalizedUrl = migrateLegacyVideoAssetUrl(input.videoUrl.trim());
  const normalizedOriginalUrl = input.originalUrl?.trim();
  const resolvedTitle = input.title?.trim() || guessTitleFromUrl(normalizedUrl) || 'Untitled study';
  const baseStudyId = deriveStudyId(resolvedTitle, normalizedUrl);
  let nextStudyId = baseStudyId;
  let suffix = 2;
  const existingStudyIds = new Set(existingItems.map((item) => item.studyId));
  while (existingStudyIds.has(nextStudyId)) {
    nextStudyId = `${baseStudyId}-${suffix}`;
    suffix += 1;
  }

  return {
    id: safeRandom(),
    studyId: nextStudyId,
    title: resolvedTitle,
    videoUrl: normalizedUrl,
    ...(normalizedOriginalUrl && normalizedOriginalUrl !== normalizedUrl
      ? { originalUrl: normalizedOriginalUrl }
      : {}),
    createdAt: new Date().toISOString()
  };
};

export const DEFAULT_VIDEO_LIBRARY: VideoLibraryItem[] = [
  {
    id: 'default-kalshi-1',
    studyId: 'kalshi-ad-1',
    title: 'Kalshi Ad 1',
    videoUrl: `${VIDEO_PROXY_PATH}/kalshi-1.mp4`,
    createdAt: '2026-03-01T00:00:00.000Z'
  },
  {
    id: 'default-kalshi-2',
    studyId: 'kalshi-ad-2',
    title: 'Kalshi Ad 2',
    videoUrl: `${VIDEO_PROXY_PATH}/kalshi-2.mp4`,
    createdAt: '2026-03-01T00:00:00.000Z'
  },
  {
    id: 'default-vrbo',
    studyId: 'vrbo-stop-searching',
    title: 'VRBO Stop Searching',
    videoUrl: `${VIDEO_PROXY_PATH}/stop-searching.mp4`,
    createdAt: '2026-03-01T00:00:00.000Z'
  },
  {
    id: 'default-countdown',
    studyId: 'countdown',
    title: 'Countdown',
    videoUrl: `${VIDEO_PROXY_PATH}/countdown.mp4`,
    createdAt: '2026-03-01T00:00:00.000Z'
  }
];

export const readVideoLibrary = (storage: Storage | null | undefined): VideoLibraryItem[] => {
  if (!storage) {
    return DEFAULT_VIDEO_LIBRARY;
  }
  const raw = storage.getItem(VIDEO_LIBRARY_STORAGE_KEY);
  if (!raw) {
    return DEFAULT_VIDEO_LIBRARY;
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    const validated = videoLibrarySchema.safeParse(parsed);
    if (!validated.success) {
      return DEFAULT_VIDEO_LIBRARY;
    }
    let didMigrate = false;
    const defaultVideoByStudyId = new Map(
      DEFAULT_VIDEO_LIBRARY.map((entry) => [entry.studyId, entry.videoUrl] as const)
    );
    const migrated = validated.data.map((item) => {
      let nextItem = item;
      const nextVideoUrl = migrateLegacyVideoAssetUrl(item.videoUrl);
      if (nextVideoUrl !== item.videoUrl) {
        nextItem = {
          ...nextItem,
          videoUrl: nextVideoUrl
        };
        didMigrate = true;
      }

      const defaultVideoUrl = defaultVideoByStudyId.get(nextItem.studyId);
      if (defaultVideoUrl && looksLikeHlsUrl(nextItem.videoUrl)) {
        const hlsSource = nextItem.videoUrl;
        nextItem = {
          ...nextItem,
          videoUrl: defaultVideoUrl,
          originalUrl: nextItem.originalUrl ?? hlsSource
        };
        didMigrate = true;
      }

      return nextItem;
    });
    if (didMigrate) {
      try {
        storage.setItem(VIDEO_LIBRARY_STORAGE_KEY, JSON.stringify(migrated));
      } catch {
        // Ignore storage write failures (private mode / restricted browser settings).
      }
    }
    return migrated;
  } catch {
    return DEFAULT_VIDEO_LIBRARY;
  }
};

export const writeVideoLibrary = (
  storage: Storage | null | undefined,
  items: VideoLibraryItem[]
): void => {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(VIDEO_LIBRARY_STORAGE_KEY, JSON.stringify(items));
  } catch {
    // Ignore storage write failures (private mode / restricted browser settings).
  }
};

export const buildStudyHref = (
  item: VideoLibraryItem,
  sequenceIndex: number
): string => {
  const paramEntries: Record<string, string> = {
    video_url: item.videoUrl,
    title: item.title,
    video_id: item.studyId,
    entry_id: item.id,
    library: WATCHLAB_LIBRARY_ID,
    index: String(sequenceIndex)
  };
  if (sequenceIndex > 0) {
    paramEntries.returning = '1';
  }
  if (item.originalUrl) {
    paramEntries.original_url = item.originalUrl;
  }
  const params = new URLSearchParams(paramEntries);
  return `/study/${encodeURIComponent(item.studyId)}?${params.toString()}`;
};

export const resolveLibraryStudy = (
  items: VideoLibraryItem[],
  studyId: string,
  preferredIndex: number | null,
  preferredId: string | null = null
): ResolvedVideoLibraryStudy | null => {
  if (preferredId) {
    const byIdIndex = items.findIndex((entry) => entry.id === preferredId);
    if (byIdIndex >= 0 && items[byIdIndex].studyId === studyId) {
      return { item: items[byIdIndex], index: byIdIndex };
    }
  }

  if (preferredIndex !== null) {
    const candidate = items[preferredIndex];
    if (candidate && candidate.studyId === studyId) {
      return { item: candidate, index: preferredIndex };
    }
  }

  const fallbackIndex = items.findIndex((entry) => entry.studyId === studyId);
  if (fallbackIndex < 0) {
    return null;
  }
  return {
    item: items[fallbackIndex],
    index: fallbackIndex
  };
};
