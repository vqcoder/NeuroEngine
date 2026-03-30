import { NextResponse } from 'next/server';
import { DEFAULT_VIDEO_LIBRARY } from '@/lib/videoLibrary';

type Context = {
  params: Promise<{ studyId: string }>;
};

type BiographVideo = {
  id: string;
  source_url: string;
};

type BiographStudy = {
  videos?: BiographVideo[];
  title?: string;
};

const fetchStudyFromBiograph = async (
  studyId: string,
): Promise<{ videoId: string; videoUrl: string; title?: string } | null> => {
  const baseUrl = process.env.BIOGRAPH_API_BASE_URL?.replace(/\/+$/, '');
  if (!baseUrl) return null;

  const token = process.env.BIOGRAPH_API_TOKEN?.trim();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(`${baseUrl}/studies/${encodeURIComponent(studyId)}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;

    const data: BiographStudy = await res.json();
    const video = data.videos?.[0];
    if (!video?.id || !video?.source_url) return null;

    return { videoId: video.id, videoUrl: video.source_url, title: data.title };
  } catch {
    return null;
  }
};

const trimNonEmpty = (value: string | null): string | null => {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const isAllowedVideoUrl = (value: string): boolean => {
  if (value.startsWith('/')) {
    return true;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

const hlsVideoPattern = /\.m3u8(?:[?#].*)?$/i;

const looksLikeHlsUrl = (value: string): boolean => {
  const lowered = value.toLowerCase();
  return (
    hlsVideoPattern.test(lowered) ||
    lowered.includes('.m3u8') ||
    /[?&](format|type)=m3u8\b/.test(lowered)
  );
};

const getDefaultStudyVideoUrl = (studyId: string): string | null => {
  const match = DEFAULT_VIDEO_LIBRARY.find((entry) => entry.studyId === studyId);
  return match?.videoUrl ?? null;
};

const normalizeVideoAssetProxyUrl = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed || trimmed.startsWith('/')) {
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
      return `/api/video-assets/${remainder}${parsed.search}${parsed.hash}`;
    }
  } catch {
    return trimmed;
  }
  return trimmed;
};

export async function GET(request: Request, context: Context) {
  const { studyId } = await context.params;
  const params = new URL(request.url).searchParams;

  const overrideTitle = trimNonEmpty(params.get('title'));
  const overrideVideoUrlRaw = trimNonEmpty(params.get('video_url'));
  const overrideVideoId = trimNonEmpty(params.get('video_id'));
  const overrideOriginalUrl = trimNonEmpty(params.get('original_url'));
  const hasConsistentOverrides = overrideVideoId === studyId;

  const normalizedOverrideVideoUrl = overrideVideoUrlRaw
    ? normalizeVideoAssetProxyUrl(overrideVideoUrlRaw)
    : null;
  const biographStudy = await fetchStudyFromBiograph(studyId);

  const defaultVideo = normalizeVideoAssetProxyUrl(process.env.DEFAULT_STUDY_VIDEO_URL || '/sample.mp4');
  const defaultStudyVideoUrl = getDefaultStudyVideoUrl(studyId);
  const fallbackVideoUrl = defaultStudyVideoUrl ?? defaultVideo;
  const title = biographStudy?.title
    ? biographStudy.title
    : hasConsistentOverrides && overrideTitle
      ? overrideTitle
      : `WatchLab Study ${studyId}`;
  const videoId = biographStudy?.videoId ?? studyId;
  const requestedVideoUrl =
    biographStudy?.videoUrl
      ? normalizeVideoAssetProxyUrl(biographStudy.videoUrl)
      :
    hasConsistentOverrides && normalizedOverrideVideoUrl && isAllowedVideoUrl(normalizedOverrideVideoUrl)
      ? normalizedOverrideVideoUrl
      : fallbackVideoUrl;
  const shouldForceDefaultStudyVideo =
    Boolean(defaultStudyVideoUrl) && looksLikeHlsUrl(requestedVideoUrl);
  const videoUrl =
    shouldForceDefaultStudyVideo && defaultStudyVideoUrl ? defaultStudyVideoUrl : requestedVideoUrl;
  const originalVideoUrl =
    !shouldForceDefaultStudyVideo && hasConsistentOverrides
      ? overrideOriginalUrl && isAllowedVideoUrl(overrideOriginalUrl)
        ? overrideOriginalUrl
        : normalizedOverrideVideoUrl && isAllowedVideoUrl(normalizedOverrideVideoUrl)
          ? normalizedOverrideVideoUrl
          : null
      : null;
  const dialEnabled = process.env.STUDY_DIAL_ENABLED === 'true';
  const requireWebcam = process.env.STUDY_REQUIRE_WEBCAM === 'true';
  const micEnabled = process.env.STUDY_MIC_ENABLED === 'true';
  // Enable client-side MediaPipe extraction: ENABLE_CLIENT_EXTRACTION=true in env vars
  const clientExtractionEnabled = process.env.ENABLE_CLIENT_EXTRACTION === 'true';

  return NextResponse.json({
    studyId,
    videoId,
    title,
    videoUrl,
    originalVideoUrl,
    dialEnabled,
    requireWebcam,
    micEnabled,
    clientExtractionEnabled
  });
}
