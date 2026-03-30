/**
 * POST /api/video/download
 *
 * Creates a study and video record in biograph-api, returning an invite URL
 * for participants.
 *
 * Required env vars:
 *   BIOGRAPH_API_BASE_URL  - e.g. "https://api.alpha-engine.ai"
 *   BIOGRAPH_API_TOKEN     - Bearer token for biograph-api
 */

import dns from 'dns/promises';
import net from 'net';
import { NextResponse } from 'next/server';
import { isHttpUrl } from '@/lib/urlUtils';

export const runtime = 'nodejs';

/**
 * SSRF protection: reject private/loopback/link-local IPs.
 * Mirrors _is_private_ip() from services/biograph_api/app/routes_prediction.py.
 */
const checkIpPrivate = (ip: string): boolean => {
  if (ip === '127.0.0.1' || ip === '::1' || ip.startsWith('127.')) return true;
  if (ip.startsWith('10.')) return true;
  if (ip.startsWith('192.168.')) return true;
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(ip)) return true;
  if (ip.startsWith('169.254.')) return true;
  if (ip.toLowerCase().startsWith('fe80:')) return true;
  if (ip.toLowerCase().startsWith('fc') || ip.toLowerCase().startsWith('fd')) return true;
  if (ip.startsWith('::ffff:')) {
    const mapped = ip.slice(7);
    if (net.isIPv4(mapped)) return checkIpPrivate(mapped);
  }
  return false;
};

const isPrivateIp = async (hostname: string): Promise<boolean> => {
  if (net.isIP(hostname)) return checkIpPrivate(hostname);
  try {
    const results = await dns.lookup(hostname, { all: true });
    return results.some((r) => checkIpPrivate(r.address));
  } catch {
    return false;
  }
};

/**
 * Platforms that block server-side video downloads.
 * Mirrors _PLATFORM_BLOCKED_HOSTNAMES from services/biograph_api/app/download_service.py.
 */
const BLOCKED_PLATFORM_RE =
  /(?:^|\.)(?:tiktok\.com|instagram\.com|twitter\.com|x\.com|facebook\.com|fb\.watch|fb\.me|linkedin\.com|snapchat\.com)$/i;

const isBlockedPlatform = (hostname: string): boolean =>
  BLOCKED_PLATFORM_RE.test(hostname.toLowerCase());

export async function POST(request: Request) {
  const biographBaseUrl = process.env.BIOGRAPH_API_BASE_URL;
  const biographToken = process.env.BIOGRAPH_API_TOKEN;

  if (!biographBaseUrl) {
    return NextResponse.json(
      { error: 'BIOGRAPH_API_BASE_URL env var is required.' },
      { status: 503 }
    );
  }

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
  const hintTitle =
    typeof (body as { title?: unknown })?.title === 'string'
      ? (body as { title: string }).title.trim()
      : '';

  if (!rawUrl || !isHttpUrl(rawUrl)) {
    return NextResponse.json({ error: 'A valid http(s) URL is required.' }, { status: 400 });
  }

  // Platform blocking: reject URLs from platforms that block server-side downloads (S9)
  try {
    const parsed = new URL(rawUrl);
    if (parsed.hostname && isBlockedPlatform(parsed.hostname)) {
      return NextResponse.json(
        {
          error:
            'This URL points to a platform that blocks server-side video downloads ' +
            '(TikTok, Instagram, Twitter/X, Facebook, LinkedIn, Snapchat). ' +
            'Download the video file and upload it directly instead.',
        },
        { status: 422 }
      );
    }
  } catch {
    /* URL already validated by isHttpUrl above */
  }

  // SSRF protection: reject URLs resolving to private/internal networks (S9)
  try {
    const parsed = new URL(rawUrl);
    if (parsed.hostname && await isPrivateIp(parsed.hostname)) {
      return NextResponse.json(
        { error: 'URLs pointing to private/internal networks are not allowed.' },
        { status: 422 }
      );
    }
  } catch { /* URL already validated by isHttpUrl above */ }

  const studyName = hintTitle || 'Untitled Study';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (biographToken) {
    headers['Authorization'] = `Bearer ${biographToken}`;
  }

  try {
    // Step 1: Create study
    const studyRes = await fetch(`${biographBaseUrl}/studies`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: studyName }),
    });
    if (!studyRes.ok) {
      const msg = await studyRes.text().catch(() => '');
      throw new Error(`Failed to create study (${studyRes.status}): ${msg}`);
    }
    const study = await studyRes.json() as { id: string };

    // Step 2: Create video record
    const videoRes = await fetch(`${biographBaseUrl}/videos`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        study_id: study.id,
        title: studyName,
        source_url: rawUrl,
      }),
    });
    if (!videoRes.ok) {
      const msg = await videoRes.text().catch(() => '');
      throw new Error(`Failed to create video (${videoRes.status}): ${msg}`);
    }
    const video = await videoRes.json() as { id: string };

    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'https://neurotrace-watchlab.vercel.app';
    const inviteUrl = `${baseUrl}/study/${study.id}`;

    return NextResponse.json({
      success: true,
      studyId: study.id,
      videoId: video.id,
      inviteUrl,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Study creation failed.' },
      { status: 400 }
    );
  }
}
