import { NextResponse } from 'next/server';
import { lookup } from 'dns/promises';
import { isHttpUrl } from '@/lib/urlUtils';

export const runtime = 'nodejs';

const HLS_CONTENT_TYPE = 'application/vnd.apple.mpegurl';

// ---------------------------------------------------------------------------
// Domain allowlist — limits which hosts this proxy will fetch from.
// By default, only known video CDN / streaming domains are allowed.
// Extend via WATCHLAB_HLS_ALLOWED_HOSTS (comma-separated hostnames).
// ---------------------------------------------------------------------------

const DEFAULT_ALLOWED_HOSTS: ReadonlySet<string> = new Set([
  // Vimeo
  'player.vimeo.com',
  'vod-progressive.akamaized.net',
  'vod-adaptive-ak.buzzfeed.com',
  // Cloudflare Stream
  'videodelivery.net',
  'customer-*.cloudflarestream.com',
  // Mux
  'stream.mux.com',
  // AWS CloudFront / S3 (common video hosting)
  'cloudfront.net',
  's3.amazonaws.com',
  // Bunny CDN
  'b-cdn.net',
  // Fastly
  'fastly.net',
  // Generic HLS / CDN
  'cdn.jwplayer.com',
  'content.jwplatform.com',
  // Biograph API assets
  'biograph-api-production.up.railway.app',
]);

const EXTRA_ALLOWED_HOSTS: ReadonlySet<string> = new Set(
  (process.env.WATCHLAB_HLS_ALLOWED_HOSTS ?? '')
    .split(',')
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean)
);

const isAllowedHost = (hostname: string): boolean => {
  const lower = hostname.toLowerCase();
  if (DEFAULT_ALLOWED_HOSTS.has(lower) || EXTRA_ALLOWED_HOSTS.has(lower)) {
    return true;
  }
  // Check suffix matches (e.g. *.cloudflarestream.com)
  for (const allowed of DEFAULT_ALLOWED_HOSTS) {
    if (allowed.startsWith('*.') && lower.endsWith(allowed.slice(1))) {
      return true;
    }
    // Also match subdomains of exact entries (e.g. d123.cloudfront.net)
    if (lower.endsWith(`.${allowed}`)) {
      return true;
    }
  }
  for (const allowed of EXTRA_ALLOWED_HOSTS) {
    if (lower.endsWith(`.${allowed}`)) {
      return true;
    }
  }
  return false;
};

/**
 * SSRF protection — block requests to private/internal IP ranges.
 * Mirrors the Python `_is_private_ip` helper in routes_prediction.py.
 */
const isPrivateIp = (ip: string): boolean => {
  // IPv6 loopback
  if (ip === '::1') return true;

  // IPv6 unique-local (fc00::/7 → fc.. or fd..)
  if (/^f[cd]/i.test(ip)) return true;

  // Normalise IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1)
  const v4 = ip.replace(/^::ffff:/i, '');

  const parts = v4.split('.').map(Number);
  if (parts.length !== 4 || parts.some((n) => Number.isNaN(n))) return false;

  const [a, b] = parts;

  if (a === 127) return true;                          // 127.0.0.0/8
  if (a === 10) return true;                           // 10.0.0.0/8
  if (a === 172 && b >= 16 && b <= 31) return true;    // 172.16.0.0/12
  if (a === 192 && b === 168) return true;             // 192.168.0.0/16
  if (a === 169 && b === 254) return true;             // 169.254.0.0/16
  if (a === 0 && parts[1] === 0 && parts[2] === 0 && parts[3] === 0) return true; // 0.0.0.0

  return false;
};

/**
 * Resolve hostname and reject if any resolved address is private.
 * Returns an error string if blocked, or null if the address is allowed.
 */
const checkSsrf = async (hostname: string): Promise<string | null> => {
  // Direct IP literal check
  if (isPrivateIp(hostname)) {
    return 'Requests to private/internal addresses are not allowed';
  }

  try {
    // Resolve hostname to catch DNS rebinding to private ranges
    const { address } = await lookup(hostname);
    if (isPrivateIp(address)) {
      return 'Requests to private/internal addresses are not allowed';
    }
  } catch {
    // DNS resolution failure — let the downstream fetch handle it
  }

  return null;
};

const isLikelyManifestResponse = (contentType: string, targetUrl: string): boolean => {
  const normalizedType = contentType.toLowerCase();
  if (
    normalizedType.includes('application/vnd.apple.mpegurl') ||
    normalizedType.includes('application/x-mpegurl')
  ) {
    return true;
  }
  return targetUrl.toLowerCase().includes('.m3u8');
};

const toProxyUrl = (rawCandidate: string, baseUrl: string): string | null => {
  try {
    const absolute = new URL(rawCandidate, baseUrl);
    if (absolute.protocol !== 'http:' && absolute.protocol !== 'https:') {
      return null;
    }
    return `/api/video/hls-proxy?url=${encodeURIComponent(absolute.toString())}`;
  } catch {
    return null;
  }
};

const rewriteAttributeUris = (line: string, baseUrl: string): string => {
  return line.replace(/URI="([^"]+)"/gi, (full, rawUri: string) => {
    const proxied = toProxyUrl(rawUri, baseUrl);
    if (!proxied) {
      return full;
    }
    return `URI="${proxied}"`;
  });
};

const rewriteManifest = (manifestText: string, manifestUrl: string): string => {
  return manifestText
    .split(/\r?\n/)
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return line;
      }
      if (trimmed.startsWith('#')) {
        return rewriteAttributeUris(line, manifestUrl);
      }
      const proxied = toProxyUrl(trimmed, manifestUrl);
      return proxied ?? line;
    })
    .join('\n');
};

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const targetRaw = params.get('url')?.trim() ?? '';
  if (!targetRaw || !isHttpUrl(targetRaw)) {
    return NextResponse.json({ error: 'A valid http(s) url query parameter is required.' }, { status: 400 });
  }

  // Domain allowlist — only proxy from known video CDN hosts
  const parsedTarget = new URL(targetRaw);
  if (!isAllowedHost(parsedTarget.hostname)) {
    return NextResponse.json(
      { error: `Host "${parsedTarget.hostname}" is not in the HLS proxy allowlist.` },
      { status: 403 }
    );
  }

  // SSRF protection — block requests targeting private/internal networks
  const ssrfError = await checkSsrf(parsedTarget.hostname);
  if (ssrfError) {
    return NextResponse.json({ error: ssrfError }, { status: 403 });
  }

  const range = request.headers.get('range');
  let upstream: Response;
  try {
    upstream = await fetch(targetRaw, {
      method: 'GET',
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        Accept: '*/*',
        ...(range ? { Range: range } : {})
      },
      cache: 'no-store',
      redirect: 'follow'
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: `HLS proxy fetch failed: ${error instanceof Error ? error.message : 'unknown error'}`
      },
      { status: 502 }
    );
  }

  if (!upstream.ok && upstream.status !== 206) {
    const bodyText = await upstream.text().catch(() => '');
    return NextResponse.json(
      {
        error: `HLS proxy upstream responded ${upstream.status}${bodyText ? `: ${bodyText.slice(0, 200)}` : ''}`
      },
      { status: 502 }
    );
  }

  const upstreamContentType = upstream.headers.get('content-type') ?? '';
  if (isLikelyManifestResponse(upstreamContentType, targetRaw)) {
    const manifest = await upstream.text();
    const rewritten = rewriteManifest(manifest, targetRaw);
    return new Response(rewritten, {
      status: upstream.status,
      headers: {
        'Content-Type': HLS_CONTENT_TYPE,
        'Cache-Control': 'no-store',
        'Access-Control-Allow-Origin': '*'
      }
    });
  }

  const headers = new Headers();
  headers.set('Content-Type', upstreamContentType || 'application/octet-stream');
  headers.set('Cache-Control', upstream.headers.get('cache-control') ?? 'public, max-age=60');
  headers.set('Access-Control-Allow-Origin', '*');
  const acceptRanges = upstream.headers.get('accept-ranges');
  if (acceptRanges) {
    headers.set('Accept-Ranges', acceptRanges);
  }
  const contentLength = upstream.headers.get('content-length');
  if (contentLength) {
    headers.set('Content-Length', contentLength);
  }
  const contentRange = upstream.headers.get('content-range');
  if (contentRange) {
    headers.set('Content-Range', contentRange);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers
  });
}
