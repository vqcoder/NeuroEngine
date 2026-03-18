import { createHash } from 'crypto';
import { spawn } from 'child_process';
import { lookup } from 'dns/promises';
import { mkdir, open, readdir, rename, stat, unlink } from 'fs/promises';
import { tmpdir } from 'os';
import path from 'path';
import { NextResponse } from 'next/server';
import { isHttpUrl } from '@/lib/urlUtils';

export const runtime = 'nodejs';

// ---------------------------------------------------------------------------
// SSRF protection — block requests to private/internal IP ranges.
// ---------------------------------------------------------------------------

const isPrivateIp = (ip: string): boolean => {
  if (ip === '::1') return true;
  if (/^f[cd]/i.test(ip)) return true;
  const v4 = ip.replace(/^::ffff:/i, '');
  const parts = v4.split('.').map(Number);
  if (parts.length !== 4 || parts.some((n) => Number.isNaN(n))) return false;
  const [a, b] = parts;
  if (a === 127) return true;
  if (a === 10) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 192 && b === 168) return true;
  if (a === 169 && b === 254) return true;
  if (a === 0 && parts[1] === 0 && parts[2] === 0 && parts[3] === 0) return true;
  return false;
};

const checkSsrf = async (hostname: string): Promise<string | null> => {
  if (isPrivateIp(hostname)) {
    return 'Requests to private/internal addresses are not allowed';
  }
  try {
    const { address } = await lookup(hostname);
    if (isPrivateIp(address)) {
      return 'Requests to private/internal addresses are not allowed';
    }
  } catch {
    // DNS resolution failure — let the downstream fetch handle it
  }
  return null;
};

const VIDEO_CACHE_DIR = path.join(tmpdir(), 'watchlab-video-cache');
const VIDEO_CACHE_MAX_BYTES = Math.max(
  Number.parseInt(process.env.WATCHLAB_VIDEO_CACHE_MAX_BYTES ?? '524288000', 10) || 524288000,
  10 * 1024 * 1024
);

const directVideoExtensionPattern = /\.(mp4|webm|ogg|m4v|mov|m3u8)(?:[?#].*)?$/i;
const cacheableVideoExtensionPattern = /\.(mp4|webm|ogg|m4v|mov)(?:[?#].*)?$/i;
const hlsVideoExtensionPattern = /\.m3u8(?:[?#].*)?$/i;
const cacheableExtensions = ['mp4', 'webm', 'ogg', 'm4v', 'mov'] as const;

const contentTypeToExtension: Record<string, string> = {
  'video/mp4': '.mp4',
  'video/webm': '.webm',
  'video/ogg': '.ogg',
  'video/quicktime': '.mov',
  'application/octet-stream': '.mp4'
};

const YT_DLP_TIMEOUT_MS = Math.max(
  Number.parseInt(process.env.WATCHLAB_VIDEO_RESOLVE_YTDLP_TIMEOUT_MS ?? '25000', 10) || 25000,
  5000
);

const isLikelyHlsUrl = (value: string): boolean => {
  const lowered = value.trim().toLowerCase();
  if (!lowered) {
    return false;
  }
  return (
    hlsVideoExtensionPattern.test(lowered) ||
    lowered.includes('.m3u8') ||
    /[?&](format|type)=m3u8\b/.test(lowered)
  );
};

const inferExtension = (url: string, contentType?: string | null): string => {
  try {
    const parsed = new URL(url);
    const pathname = parsed.pathname.toLowerCase();
    if (pathname.endsWith('.mp4')) return '.mp4';
    if (pathname.endsWith('.webm')) return '.webm';
    if (pathname.endsWith('.ogg')) return '.ogg';
    if (pathname.endsWith('.m4v')) return '.m4v';
    if (pathname.endsWith('.mov')) return '.mov';
    if (pathname.endsWith('.m3u8')) return '.m3u8';
  } catch {
    // ignore and fall through
  }

  const normalizedContentType = (contentType ?? '').split(';')[0].trim().toLowerCase();
  if (normalizedContentType in contentTypeToExtension) {
    return contentTypeToExtension[normalizedContentType];
  }
  return '.mp4';
};

const parseVimeoVideoId = (rawUrl: string): string | null => {
  try {
    const parsed = new URL(rawUrl);
    const hostname = parsed.hostname.toLowerCase();
    if (!hostname.includes('vimeo.com')) {
      return null;
    }
    const segments = parsed.pathname.split('/').filter(Boolean);
    for (let index = segments.length - 1; index >= 0; index -= 1) {
      if (/^\d+$/.test(segments[index])) {
        return segments[index];
      }
    }
    return null;
  } catch {
    return null;
  }
};

const normalizeInputUrl = (rawUrl: string): string => {
  try {
    const parsed = new URL(rawUrl);
    parsed.hash = '';

    const vimeoId = parseVimeoVideoId(rawUrl);
    if (vimeoId && parsed.hostname.toLowerCase().includes('vimeo.com')) {
      return `https://vimeo.com/${vimeoId}`;
    }

    return parsed.toString();
  } catch {
    return rawUrl;
  }
};

const fetchWithTimeout = async (
  url: string,
  timeoutMs = 10000,
  extraHeaders?: Record<string, string>
): Promise<Response> => {
  // SSRF check before every outbound fetch
  const parsed = new URL(url);
  const ssrfError = await checkSsrf(parsed.hostname);
  if (ssrfError) {
    throw new Error(ssrfError);
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      method: 'GET',
      redirect: 'follow',
      signal: controller.signal,
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        Accept: 'application/json,text/html,video/*,*/*;q=0.8',
        ...(extraHeaders ?? {})
      }
    });
  } finally {
    clearTimeout(timeoutId);
  }
};

const resolveFromVimeoConfig = (config: {
  request?: {
    files?: {
      progressive?: Array<{
        url?: string;
        width?: number;
        height?: number;
      }>;
      hls?: {
        default_cdn?: string;
        cdns?: Record<string, { url?: string }>;
      };
    };
  };
}): { resolvedUrl: string; strategy: string } | null => {
  const progressive = config.request?.files?.progressive ?? [];
  const rankedProgressive = progressive
    .filter((entry) => typeof entry.url === 'string' && isHttpUrl(entry.url))
    .map((entry) => ({
      url: entry.url as string,
      width: Number(entry.width ?? 0),
      height: Number(entry.height ?? 0)
    }))
    .sort((left, right) => right.height - left.height || right.width - left.width);

  if (rankedProgressive.length > 0) {
    return {
      resolvedUrl: rankedProgressive[0].url,
      strategy: 'vimeo-progressive'
    };
  }

  const defaultCdn = config.request?.files?.hls?.default_cdn;
  const hlsUrl = defaultCdn ? config.request?.files?.hls?.cdns?.[defaultCdn]?.url : undefined;
  if (typeof hlsUrl === 'string' && isHttpUrl(hlsUrl)) {
    return {
      resolvedUrl: hlsUrl,
      strategy: 'vimeo-hls'
    };
  }

  return null;
};

const resolveFromVimeo = async (
  rawUrl: string
): Promise<{ resolvedUrl: string; strategy: string } | null> => {
  const vimeoId = parseVimeoVideoId(rawUrl);
  if (!vimeoId) {
    return null;
  }

  const configResponse = await fetchWithTimeout(`https://player.vimeo.com/video/${vimeoId}/config`, 12000, {
    Accept: 'application/json, text/plain, */*',
    Referer: rawUrl,
    Origin: 'https://vimeo.com'
  });
  if (!configResponse.ok) {
    throw new Error(`Vimeo config lookup failed (${configResponse.status}).`);
  }

  const config = (await configResponse.json()) as {
    request?: {
      files?: {
        progressive?: Array<{
          url?: string;
          width?: number;
          height?: number;
        }>;
        hls?: {
          default_cdn?: string;
          cdns?: Record<string, { url?: string }>;
        };
      };
    };
  };

  const resolved = resolveFromVimeoConfig(config);
  if (resolved) {
    return resolved;
  }

  try {
    const playerPageResponse = await fetchWithTimeout(
      `https://player.vimeo.com/video/${vimeoId}`,
      12000,
      {
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        Referer: rawUrl
      }
    );
    if (playerPageResponse.ok) {
      const playerHtml = await playerPageResponse.text();
      const playerConfigUrl = extractVimeoConfigUrlFromHtml(
        playerHtml,
        `https://player.vimeo.com/video/${vimeoId}`
      );
      if (playerConfigUrl) {
        const resolvedFromPlayerConfig = await resolveFromVimeoConfigUrl(playerConfigUrl, rawUrl);
        if (resolvedFromPlayerConfig) {
          return {
            resolvedUrl: resolvedFromPlayerConfig.resolvedUrl,
            strategy: 'vimeo-player-config-url'
          };
        }
      }

      const playerCandidates = extractVideoCandidatesFromHtml(
        playerHtml,
        `https://player.vimeo.com/video/${vimeoId}`
      ).filter((entry) => directVideoExtensionPattern.test(entry));
      if (playerCandidates.length > 0) {
        return {
          resolvedUrl: playerCandidates[0],
          strategy: 'vimeo-player-html-candidate'
        };
      }
    }
  } catch {
    // Continue with generic fallback.
  }

  throw new Error('No playable Vimeo source was found for this link.');
};

const decodeCandidate = (value: string): string => {
  return value
    .replace(/\\u002F/gi, '/')
    .replace(/\\\//g, '/')
    .replace(/&amp;/gi, '&')
    .trim();
};

const normalizeAbsoluteHttpUrl = (candidate: string, baseUrl: string): string | null => {
  const decoded = decodeCandidate(candidate);
  if (!decoded) {
    return null;
  }
  try {
    const parsed = new URL(decoded, baseUrl);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
};

const extractVimeoConfigUrlFromHtml = (html: string, baseUrl: string): string | null => {
  const patterns: RegExp[] = [
    /"config_url"\s*:\s*"([^"]+)"/i,
    /data-config-url=["']([^"']+)["']/i,
    /https:\/\/player\.vimeo\.com\/video\/\d+\/config[^"'<\s]*/i
  ];

  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (!match) {
      continue;
    }
    const candidate = match[1] ?? match[0];
    const normalized = normalizeAbsoluteHttpUrl(candidate, baseUrl);
    if (normalized) {
      return normalized;
    }
  }

  return null;
};

const resolveFromVimeoConfigUrl = async (
  configUrl: string,
  refererUrl: string
): Promise<{ resolvedUrl: string; strategy: string } | null> => {
  const response = await fetchWithTimeout(configUrl, 12000, {
    Accept: 'application/json, text/plain, */*',
    Referer: refererUrl,
    Origin: 'https://vimeo.com'
  });
  if (!response.ok) {
    throw new Error(`Vimeo config URL lookup failed (${response.status}).`);
  }
  const config = (await response.json()) as Parameters<typeof resolveFromVimeoConfig>[0];
  const resolved = resolveFromVimeoConfig(config);
  if (!resolved) {
    return null;
  }
  return {
    resolvedUrl: resolved.resolvedUrl,
    strategy: 'vimeo-config-url'
  };
};

const extractVideoCandidatesFromHtml = (html: string, baseUrl: string): string[] => {
  const candidates: string[] = [];
  const seen = new Set<string>();

  const push = (raw: string) => {
    const normalized = normalizeAbsoluteHttpUrl(raw, baseUrl);
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    candidates.push(normalized);
  };

  const patterns: RegExp[] = [
    /<meta[^>]+property=["']og:video(?::url|:secure_url)?["'][^>]+content=["']([^"']+)["'][^>]*>/gi,
    /<meta[^>]+name=["']twitter:player:stream["'][^>]+content=["']([^"']+)["'][^>]*>/gi,
    /<source[^>]+src=["']([^"']+)["'][^>]*>/gi,
    /<video[^>]+src=["']([^"']+)["'][^>]*>/gi,
    /"contentUrl"\s*:\s*"([^"]+)"/gi,
    /"videoUrl"\s*:\s*"([^"]+)"/gi,
    /"url"\s*:\s*"([^"]+\.(?:mp4|webm|ogg|m4v|mov|m3u8)[^"]*)"/gi,
    /https?:\\\/\\\/[^"'\\\s>]+\.(?:mp4|webm|ogg|m4v|mov|m3u8)(?:\?[^"'\\\s>]*)?/gi,
    /https?:\/\/[^"'\\\s>]+\.(?:mp4|webm|ogg|m4v|mov|m3u8)(?:\?[^"'\\\s>]*)?/gi
  ];

  for (const pattern of patterns) {
    for (const match of html.matchAll(pattern)) {
      const value = match[1] ?? match[0];
      if (value) {
        push(value);
      }
    }
  }

  return candidates;
};

const resolveFromGenericWebPage = async (
  rawUrl: string
): Promise<{ resolvedUrl: string; strategy: string }> => {
  const response = await fetchWithTimeout(rawUrl, 12000);
  if (!response.ok) {
    throw new Error(`Webpage fetch failed (${response.status}).`);
  }

  const finalUrl = response.url || rawUrl;
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';

  if (contentType.startsWith('video/')) {
    return {
      resolvedUrl: finalUrl,
      strategy: 'direct-content-type'
    };
  }

  if (!contentType.includes('text/html')) {
    if (directVideoExtensionPattern.test(finalUrl)) {
      return {
        resolvedUrl: finalUrl,
        strategy: 'direct-extension'
      };
    }
    throw new Error('This link did not resolve to a playable video page.');
  }

  const html = await response.text();
  const vimeoConfigUrl = extractVimeoConfigUrlFromHtml(html, finalUrl);
  if (vimeoConfigUrl) {
    try {
      const resolvedFromConfigUrl = await resolveFromVimeoConfigUrl(vimeoConfigUrl, finalUrl);
      if (resolvedFromConfigUrl) {
        return resolvedFromConfigUrl;
      }
    } catch {
      // Continue with generic extraction fallback.
    }
  }

  const candidates = extractVideoCandidatesFromHtml(html, finalUrl).filter((entry) =>
    directVideoExtensionPattern.test(entry)
  );

  if (candidates.length === 0) {
    throw new Error('No playable video source found on the webpage.');
  }

  const finalHost = new URL(finalUrl).hostname;
  const ranked = [...candidates].sort((left, right) => {
    const leftUrl = new URL(left);
    const rightUrl = new URL(right);
    const leftScore =
      (left.toLowerCase().includes('.mp4') ? 3 : 1) + (leftUrl.hostname === finalHost ? 2 : 0);
    const rightScore =
      (right.toLowerCase().includes('.mp4') ? 3 : 1) + (rightUrl.hostname === finalHost ? 2 : 0);
    return rightScore - leftScore;
  });

  return {
    resolvedUrl: ranked[0],
    strategy: 'html-candidate'
  };
};

const cacheVideoLocally = async (
  directUrl: string
): Promise<{ videoUrl: string; cacheKey?: string; downloaded: boolean }> => {
  if (!cacheableVideoExtensionPattern.test(directUrl)) {
    return {
      videoUrl: directUrl,
      downloaded: false
    };
  }

  await mkdir(VIDEO_CACHE_DIR, { recursive: true });

  const directHash = createHash('sha256').update(directUrl).digest('hex').slice(0, 24);
  const extension = inferExtension(directUrl);
  const cacheKey = `${directHash}${extension}`;
  const cachedPath = path.join(VIDEO_CACHE_DIR, cacheKey);

  try {
    const existing = await stat(cachedPath);
    if (existing.isFile() && existing.size > 0) {
      return {
        videoUrl: `/api/video/cache/${encodeURIComponent(cacheKey)}`,
        cacheKey,
        downloaded: false
      };
    }
  } catch {
    // Cache miss, continue.
  }

  const response = await fetchWithTimeout(directUrl, 20000);
  if (!response.ok || !response.body) {
    throw new Error(`Video download failed (${response.status}).`);
  }

  const contentLength = Number.parseInt(response.headers.get('content-length') ?? '0', 10);
  if (Number.isFinite(contentLength) && contentLength > VIDEO_CACHE_MAX_BYTES) {
    throw new Error(
      `Video file is too large to cache (${Math.round(contentLength / (1024 * 1024))} MB).`
    );
  }

  const contentType = response.headers.get('content-type');
  if (contentType && !contentType.toLowerCase().startsWith('video/')) {
    throw new Error(`Resolved source is not a video stream (${contentType}).`);
  }

  const tmpPath = `${cachedPath}.tmp-${Date.now()}`;
  const fileHandle = await open(tmpPath, 'w');
  const reader = response.body.getReader();
  let written = 0;

  try {
    while (true) {
      const next = await reader.read();
      if (next.done) {
        break;
      }
      const chunk = next.value;
      if (!chunk) {
        continue;
      }
      written += chunk.byteLength;
      if (written > VIDEO_CACHE_MAX_BYTES) {
        throw new Error(
          `Video exceeded local cache limit of ${Math.round(VIDEO_CACHE_MAX_BYTES / (1024 * 1024))} MB.`
        );
      }
      await fileHandle.write(chunk);
    }
  } catch (error) {
    await fileHandle.close();
    await unlink(tmpPath).catch(() => undefined);
    throw error;
  }

  await fileHandle.close();
  await rename(tmpPath, cachedPath);

  return {
    videoUrl: `/api/video/cache/${encodeURIComponent(cacheKey)}`,
    cacheKey,
    downloaded: true
  };
};

const resolveWithYtDlp = async (
  rawUrl: string
): Promise<{ resolvedUrl: string; strategy: string } | null> => {
  const args = [
    '--no-playlist',
    '--get-url',
    '--format',
    'best[ext=mp4]/best',
    rawUrl
  ];

  return await new Promise((resolve, reject) => {
    const child = spawn('yt-dlp', args, { stdio: ['ignore', 'pipe', 'pipe'] });

    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timeoutId = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, YT_DLP_TIMEOUT_MS);

    child.stdout.on('data', (chunk: Buffer | string) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk: Buffer | string) => {
      stderr += chunk.toString();
    });

    child.on('error', (error) => {
      clearTimeout(timeoutId);
      const maybeEnoent = error as NodeJS.ErrnoException;
      if (maybeEnoent?.code === 'ENOENT') {
        reject(
          new Error(
            'yt-dlp is not installed on the machine running WatchLab.'
          )
        );
        return;
      }
      reject(error);
    });

    child.on('close', (code) => {
      clearTimeout(timeoutId);
      if (timedOut) {
        reject(new Error('yt-dlp timed out while resolving this link.'));
        return;
      }
      if (code !== 0) {
        const message = stderr.trim() || `yt-dlp exited with status ${code}`;
        reject(new Error(message));
        return;
      }

      const candidates = stdout
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0 && isHttpUrl(line));
      if (candidates.length === 0) {
        resolve(null);
        return;
      }
      const preferred = candidates.find((entry) => directVideoExtensionPattern.test(entry)) ?? candidates[0];
      resolve({
        resolvedUrl: preferred,
        strategy: 'yt-dlp'
      });
    });
  });
};

const findExistingCachedAsset = async (baseHash: string): Promise<string | null> => {
  for (const extension of cacheableExtensions) {
    const cacheKey = `${baseHash}.${extension}`;
    const candidatePath = path.join(VIDEO_CACHE_DIR, cacheKey);
    try {
      const info = await stat(candidatePath);
      if (info.isFile() && info.size > 0) {
        return cacheKey;
      }
    } catch {
      // Continue checking other extensions.
    }
  }
  return null;
};

const cacheVideoViaYtDlpDownload = async (
  rawUrl: string
): Promise<{ videoUrl: string; cacheKey: string; downloaded: boolean } | null> => {
  await mkdir(VIDEO_CACHE_DIR, { recursive: true });

  const baseHash = createHash('sha256').update(rawUrl).digest('hex').slice(0, 24);
  const existingCacheKey = await findExistingCachedAsset(baseHash);
  if (existingCacheKey) {
    return {
      videoUrl: `/api/video/cache/${encodeURIComponent(existingCacheKey)}`,
      cacheKey: existingCacheKey,
      downloaded: false
    };
  }

  const tempPrefix = `${baseHash}.tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const outputTemplate = path.join(VIDEO_CACHE_DIR, `${tempPrefix}.%(ext)s`);
  const args = [
    '--no-playlist',
    '--format',
    'best[ext=mp4]/best',
    '--merge-output-format',
    'mp4',
    '--output',
    outputTemplate,
    rawUrl
  ];

  await new Promise<void>((resolve, reject) => {
    const child = spawn('yt-dlp', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    let timedOut = false;
    const timeoutId = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, Math.max(YT_DLP_TIMEOUT_MS * 3, 30000));

    child.stderr.on('data', (chunk: Buffer | string) => {
      stderr += chunk.toString();
    });

    child.on('error', (error) => {
      clearTimeout(timeoutId);
      const maybeEnoent = error as NodeJS.ErrnoException;
      if (maybeEnoent?.code === 'ENOENT') {
        reject(new Error('yt-dlp is not installed on the machine running WatchLab.'));
        return;
      }
      reject(error);
    });

    child.on('close', (code) => {
      clearTimeout(timeoutId);
      if (timedOut) {
        reject(new Error('yt-dlp timed out while downloading this source.'));
        return;
      }
      if (code !== 0) {
        reject(new Error(stderr.trim() || `yt-dlp exited with status ${code}`));
        return;
      }
      resolve();
    });
  });

  const entries = await readdir(VIDEO_CACHE_DIR).catch(() => []);
  const downloadedFiles = entries
    .filter((entry) => entry.startsWith(`${tempPrefix}.`))
    .map((entry) => ({
      name: entry,
      extension: entry.split('.').pop()?.toLowerCase() ?? ''
    }))
    .filter((entry) => cacheableExtensions.includes(entry.extension as (typeof cacheableExtensions)[number]))
    .sort((left, right) => {
      if (left.extension === right.extension) {
        return left.name.localeCompare(right.name);
      }
      if (left.extension === 'mp4') {
        return -1;
      }
      if (right.extension === 'mp4') {
        return 1;
      }
      return left.name.localeCompare(right.name);
    });

  if (downloadedFiles.length === 0) {
    return null;
  }

  const selected = downloadedFiles[0];
  const selectedPath = path.join(VIDEO_CACHE_DIR, selected.name);
  const selectedInfo = await stat(selectedPath);
  if (!selectedInfo.isFile() || selectedInfo.size <= 0) {
    throw new Error('yt-dlp produced an empty file.');
  }
  if (selectedInfo.size > VIDEO_CACHE_MAX_BYTES) {
    throw new Error(
      `Video exceeded local cache limit of ${Math.round(VIDEO_CACHE_MAX_BYTES / (1024 * 1024))} MB.`
    );
  }

  const finalCacheKey = `${baseHash}.${selected.extension}`;
  const finalPath = path.join(VIDEO_CACHE_DIR, finalCacheKey);
  await unlink(finalPath).catch(() => undefined);
  await rename(selectedPath, finalPath);

  for (const extra of downloadedFiles.slice(1)) {
    await unlink(path.join(VIDEO_CACHE_DIR, extra.name)).catch(() => undefined);
  }

  return {
    videoUrl: `/api/video/cache/${encodeURIComponent(finalCacheKey)}`,
    cacheKey: finalCacheKey,
    downloaded: true
  };
};

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON request body.' }, { status: 400 });
  }

  const rawUrl =
    typeof (body as { url?: unknown })?.url === 'string'
      ? (body as { url: string }).url.trim()
      : '';
  if (!rawUrl || !isHttpUrl(rawUrl)) {
    return NextResponse.json({ error: 'A valid http(s) URL is required.' }, { status: 400 });
  }

  const normalizedUrl = normalizeInputUrl(rawUrl);

  // SSRF check on the input URL itself
  try {
    const inputParsed = new URL(normalizedUrl);
    const ssrfError = await checkSsrf(inputParsed.hostname);
    if (ssrfError) {
      return NextResponse.json({ error: ssrfError }, { status: 403 });
    }
  } catch {
    return NextResponse.json({ error: 'Invalid URL.' }, { status: 400 });
  }

  try {
    let resolved: { resolvedUrl: string; strategy: string } | null = null;
    let vimeoError: string | null = null;
    let genericError: string | null = null;

    try {
      resolved = await resolveFromVimeo(normalizedUrl);
    } catch (error) {
      vimeoError =
        error instanceof Error ? error.message : 'Vimeo resolver failed unexpectedly.';
    }

    if (!resolved) {
      try {
        resolved = await resolveFromGenericWebPage(normalizedUrl);
      } catch (fallbackError) {
        genericError =
          fallbackError instanceof Error
            ? fallbackError.message
            : 'Webpage fallback failed unexpectedly.';
      }
    }

    if (!resolved) {
      try {
        resolved = await resolveWithYtDlp(normalizedUrl);
      } catch (ytDlpError) {
        const ytDlpMessage =
          ytDlpError instanceof Error ? ytDlpError.message : 'yt-dlp resolution failed unexpectedly.';
        const parts = [vimeoError, genericError, `yt-dlp fallback failed: ${ytDlpMessage}`].filter(
          (part): part is string => Boolean(part && part.trim().length > 0)
        );
        throw new Error(parts.join(' '));
      }
    }

    if (!resolved) {
      const parts = [vimeoError, genericError, 'No playable source could be resolved.'].filter(
        (part): part is string => Boolean(part && part.trim().length > 0)
      );
      throw new Error(parts.join(' '));
    }

    const resolverWarnings: string[] = [];
    if (isLikelyHlsUrl(resolved.resolvedUrl)) {
      try {
        const ytDlpResolved =
          (await resolveWithYtDlp(normalizedUrl)) ??
          (await resolveWithYtDlp(resolved.resolvedUrl));
        if (ytDlpResolved && !isLikelyHlsUrl(ytDlpResolved.resolvedUrl)) {
          resolved = {
            resolvedUrl: ytDlpResolved.resolvedUrl,
            strategy: `${resolved.strategy}+yt-dlp-direct`
          };
        }
      } catch (hlsResolveError) {
        resolverWarnings.push(
          hlsResolveError instanceof Error
            ? `hls_direct_resolution_failed:${hlsResolveError.message}`
            : 'hls_direct_resolution_failed'
        );
      }
    }

    if (isLikelyHlsUrl(resolved.resolvedUrl)) {
      try {
        const downloadedCache = await cacheVideoViaYtDlpDownload(normalizedUrl);
        if (downloadedCache) {
          return NextResponse.json({
            inputUrl: rawUrl,
            normalizedInputUrl: normalizedUrl,
            resolvedUrl: resolved.resolvedUrl,
            videoUrl: downloadedCache.videoUrl,
            strategy: `${resolved.strategy}+yt-dlp-download-cache`,
            downloaded: downloadedCache.downloaded,
            cacheKey: downloadedCache.cacheKey,
            warnings: resolverWarnings
          });
        }
      } catch (hlsDownloadError) {
        resolverWarnings.push(
          hlsDownloadError instanceof Error
            ? `hls_download_cache_failed:${hlsDownloadError.message}`
            : 'hls_download_cache_failed'
        );
      }
    }

    const cacheResult = await cacheVideoLocally(resolved.resolvedUrl);

    return NextResponse.json({
      inputUrl: rawUrl,
      normalizedInputUrl: normalizedUrl,
      resolvedUrl: resolved.resolvedUrl,
      videoUrl: cacheResult.videoUrl,
      strategy: resolved.strategy,
      downloaded: cacheResult.downloaded,
      cacheKey: cacheResult.cacheKey ?? null,
      warnings: resolverWarnings
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : 'Unable to resolve the provided webpage link to a playable video.'
      },
      { status: 400 }
    );
  }
}
