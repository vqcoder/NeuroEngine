import { NextRequest, NextResponse } from 'next/server';

/**
 * Middleware that gates admin/researcher API routes behind a bearer token.
 *
 * Participant-facing routes (study config, session upload, survey chat,
 * video-assets proxy, HLS proxy, cache) remain open so participants can
 * complete studies without credentials.
 *
 * Set WATCHLAB_API_TOKEN env var to enable. When unset, all routes are open
 * (suitable for local dev).
 */

const ADMIN_API_PREFIXES = [
  '/api/video/download',
  '/api/video/resolve',
];

function isAdminRoute(pathname: string): boolean {
  return ADMIN_API_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}

export function middleware(request: NextRequest) {
  if (!isAdminRoute(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const token = process.env.WATCHLAB_API_TOKEN?.trim();
  if (!token) {
    // No token configured — allow through (local dev).
    return NextResponse.next();
  }

  const authHeader = request.headers.get('authorization') ?? '';
  if (authHeader.startsWith('Bearer ') && authHeader.slice(7) === token) {
    return NextResponse.next();
  }

  return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 });
}

export const config = {
  matcher: '/api/:path*',
};
