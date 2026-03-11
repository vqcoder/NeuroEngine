import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

type Context = {
  params: Promise<{ filename: string }>;
};

const FILENAME_PATTERN = /^[\w-]+\.(mp4|webm|mov|m4v)$/i;
const DEFAULT_UPSTREAM_ORIGIN = 'https://biograph-api-production.up.railway.app';

const resolveUpstreamOrigin = (): string => {
  const configured = process.env.VIDEO_ASSET_PROXY_ORIGIN?.trim();
  const candidate = configured && configured.length > 0 ? configured : DEFAULT_UPSTREAM_ORIGIN;
  return candidate.replace(/\/+$/, '');
};

export async function GET(request: Request, context: Context) {
  const { filename } = await context.params;
  if (!FILENAME_PATTERN.test(filename)) {
    return NextResponse.json({ error: 'Invalid filename.' }, { status: 400 });
  }

  const upstreamUrl = `${resolveUpstreamOrigin()}/video-assets/${encodeURIComponent(filename)}`;
  const rangeHeader = request.headers.get('range');

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method: 'GET',
      headers: rangeHeader ? { Range: rangeHeader } : undefined,
      cache: 'no-store'
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: `Video proxy fetch failed: ${error instanceof Error ? error.message : 'unknown error'}`
      },
      { status: 502 }
    );
  }

  if (!upstream.ok && upstream.status !== 206) {
    const detail = await upstream.text().catch(() => '');
    return NextResponse.json(
      {
        error: `Video proxy upstream responded ${upstream.status}${detail ? `: ${detail.slice(0, 180)}` : ''}`
      },
      { status: 502 }
    );
  }

  const headers = new Headers();
  headers.set('Content-Type', upstream.headers.get('content-type') ?? 'video/mp4');
  headers.set('Accept-Ranges', upstream.headers.get('accept-ranges') ?? 'bytes');
  headers.set('Cache-Control', upstream.headers.get('cache-control') ?? 'public, max-age=3600');

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
