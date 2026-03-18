/**
 * POST /api/video/download
 *
 * Downloads a video via yt-dlp and uploads it as a GitHub Release asset,
 * returning a stable permanent URL. No cloud account needed beyond the
 * existing GitHub repo.
 *
 * Required env vars:
 *   GITHUB_TOKEN   - personal access token with repo + write:packages scope
 *   GITHUB_REPO    - owner/repo (e.g. "johnvqcapital/neurotrace")
 *
 * Optional:
 *   GITHUB_RELEASE_TAG - release tag to upload assets to (default: "video-assets")
 */

import { spawn } from 'child_process';
import dns from 'dns/promises';
import { createReadStream } from 'fs';
import { mkdir, stat, unlink, readdir } from 'fs/promises';
import net from 'net';
import { tmpdir } from 'os';
import path from 'path';
import { NextResponse } from 'next/server';
import { isHttpUrl } from '@/lib/urlUtils';

export const runtime = 'nodejs';

const DOWNLOAD_DIR = path.join(tmpdir(), 'watchlab-video-downloads');
const YT_DLP_TIMEOUT_MS = Math.max(
  Number.parseInt(process.env.WATCHLAB_VIDEO_DOWNLOAD_TIMEOUT_MS ?? '180000', 10) || 180000,
  15000
);

const GITHUB_API = 'https://api.github.com';

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

const sanitizeAssetName = (name: string, ext: string): string => {
  const base = name.replace(/[^\w\-_.]/g, '-').replace(/-+/g, '-').slice(0, 60).toLowerCase();
  return `${base || 'video'}.${ext}`;
};

async function getReleaseId(repo: string, tag: string, token: string): Promise<number> {
  const res = await fetch(`${GITHUB_API}/repos/${repo}/releases/tags/${tag}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' }
  });
  if (res.ok) {
    const data = await res.json() as { id: number };
    return data.id;
  }
  // Create release if it doesn't exist
  const create = await fetch(`${GITHUB_API}/repos/${repo}/releases`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ tag_name: tag, name: 'WatchLab Video Assets', body: 'Stable hosted videos for WatchLab studies.' })
  });
  if (!create.ok) throw new Error(`Failed to create GitHub release (${create.status})`);
  const data = await create.json() as { id: number };
  return data.id;
}

const buildProxyAssetUrl = (filename: string): string =>
  `/api/video-assets/${encodeURIComponent(filename)}`;

async function hasExistingAsset(
  repo: string,
  releaseId: number,
  filename: string,
  token: string
): Promise<boolean> {
  const res = await fetch(`${GITHUB_API}/repos/${repo}/releases/${releaseId}/assets`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' }
  });
  if (!res.ok) return false;
  const assets = await res.json() as Array<{ name: string }>;
  return assets.some((asset) => asset.name === filename);
}

async function uploadAsset(
  repo: string,
  releaseId: number,
  filePath: string,
  filename: string,
  token: string
): Promise<void> {
  const fileStat = await stat(filePath);
  const stream = createReadStream(filePath);

  const res = await fetch(
    `https://uploads.github.com/repos/${repo}/releases/${releaseId}/assets?name=${encodeURIComponent(filename)}`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'video/mp4',
        'Content-Length': String(fileStat.size)
      },
      // @ts-expect-error - Node fetch supports ReadStream body
      body: stream,
      duplex: 'half'
    }
  );
  if (!res.ok) {
    const msg = await res.text().catch(() => '');
    throw new Error(`GitHub asset upload failed (${res.status}): ${msg}`);
  }
  await res.json().catch(() => null);
}

export async function POST(request: Request) {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  const tag = process.env.GITHUB_RELEASE_TAG ?? 'video-assets';

  if (!token || !repo) {
    return NextResponse.json(
      { error: 'GITHUB_TOKEN and GITHUB_REPO env vars are required.' },
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

  await mkdir(DOWNLOAD_DIR, { recursive: true });
  const tmpBase = `dl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const tmpTemplate = path.join(DOWNLOAD_DIR, `${tmpBase}.%(ext)s`);

  const baseArgs = [
    '--no-playlist',
    '--format', 'best[ext=mp4]/best',
    '--merge-output-format', 'mp4',
    '--output', tmpTemplate,
    // Use Node.js as the JS runtime for YouTube extraction (yt-dlp 2025+)
    // Runtime name must be "node" not "nodejs" per yt-dlp docs.
    '--js-runtimes', 'node',
    // Enable remote EJS challenge solver for YouTube's n-parameter decoding.
    '--remote-components', 'ejs:github',
  ];

  // YouTube cookie support — same env var as biograph_api
  const cookiesContent = (process.env.YOUTUBE_COOKIES_NETSCAPE ?? '').trim();
  let cookiesPath: string | null = null;
  if (cookiesContent) {
    cookiesPath = path.join(tmpdir(), 'yt-cookies-watchlab.txt');
    const { writeFileSync } = await import('fs');
    writeFileSync(cookiesPath, cookiesContent.endsWith('\n') ? cookiesContent : cookiesContent + '\n');
  }

  // Residential proxy support — same env var as biograph_api
  const proxyUrl = (process.env.YTDLP_PROXY ?? '').trim();

  /**
   * Run yt-dlp with the given args. Returns the stderr output on failure.
   */
  const runYtDlp = (args: string[]): Promise<{ ok: boolean; stderr: string }> =>
    new Promise((resolve) => {
      const child = spawn('yt-dlp', args, { stdio: ['ignore', 'pipe', 'pipe'] });
      let stderr = '';
      let timedOut = false;
      const timeoutId = setTimeout(() => {
        timedOut = true;
        child.kill('SIGTERM');
      }, YT_DLP_TIMEOUT_MS);

      child.stderr.on('data', (chunk: Buffer | string) => { stderr += chunk.toString(); });
      child.on('error', (error) => {
        clearTimeout(timeoutId);
        const maybeEnoent = error as NodeJS.ErrnoException;
        if (maybeEnoent?.code === 'ENOENT') {
          resolve({ ok: false, stderr: 'yt-dlp is not installed on this server.' });
          return;
        }
        resolve({ ok: false, stderr: error.message });
      });
      child.on('close', (code) => {
        clearTimeout(timeoutId);
        if (timedOut) { resolve({ ok: false, stderr: 'Download timed out.' }); return; }
        if (code !== 0) { resolve({ ok: false, stderr: stderr.trim() || `yt-dlp exited with status ${code}` }); return; }
        resolve({ ok: true, stderr });
      });
    });

  const findDownloadedFile = async (): Promise<string | null> => {
    for (const ext of ['mp4', 'webm', 'mkv', 'mov', 'm4v']) {
      const candidate = path.join(DOWNLOAD_DIR, `${tmpBase}.${ext}`);
      try {
        const s = await stat(candidate);
        if (s.isFile() && s.size > 0) return candidate;
      } catch { /* try next */ }
    }
    return null;
  };

  let downloadedPath: string | null = null;

  try {
    // Build args with optional cookies and proxy.
    const buildArgs = (opts: { useCookies: boolean; useProxy: boolean }): string[] => {
      const args = [...baseArgs];
      if (opts.useCookies && cookiesPath) args.push('--cookies', cookiesPath);
      if (opts.useProxy && proxyUrl) args.push('--proxy', proxyUrl);
      args.push(rawUrl);
      return args;
    };

    const cleanPartial = async () => {
      const partial = await findDownloadedFile();
      if (partial) await unlink(partial).catch(() => undefined);
    };

    // Attempt 1: cookies + proxy (full features)
    let result = await runYtDlp(buildArgs({ useCookies: !!cookiesPath, useProxy: !!proxyUrl }));

    // Attempt 2: If proxy caused SSL/connection error, retry WITHOUT proxy.
    // Residential proxies can drop long-lived video download streams.
    if (!result.ok && proxyUrl) {
      const lowerErr = result.stderr.toLowerCase();
      if (
        lowerErr.includes('ssl') ||
        lowerErr.includes('unexpected_eof') ||
        lowerErr.includes('connection reset') ||
        lowerErr.includes('timed out') ||
        lowerErr.includes('urlopen error')
      ) {
        await cleanPartial();
        console.log('[video/download] Retrying WITHOUT proxy after SSL/connection error:', result.stderr.slice(0, 200));
        result = await runYtDlp(buildArgs({ useCookies: !!cookiesPath, useProxy: false }));
      }
    }

    // Attempt 3: If cookies caused the error, retry without cookies (keep proxy off if it was already dropped).
    if (!result.ok && cookiesPath) {
      const lowerErr = result.stderr.toLowerCase();
      if (
        lowerErr.includes('cookies') ||
        lowerErr.includes('sign in') ||
        lowerErr.includes('not available')
      ) {
        await cleanPartial();
        console.log('[video/download] Retrying without cookies after failure:', result.stderr.slice(0, 200));
        result = await runYtDlp(buildArgs({ useCookies: false, useProxy: false }));
      }
    }

    if (!result.ok) {
      throw new Error(result.stderr);
    }

    downloadedPath = await findDownloadedFile();

    if (!downloadedPath) {
      return NextResponse.json({ error: 'Download completed but output file was not found.' }, { status: 500 });
    }

    const ext = path.extname(downloadedPath).slice(1).toLowerCase() || 'mp4';
    const assetName = sanitizeAssetName(hintTitle || path.basename(downloadedPath, `.${ext}`), ext);

    const releaseId = await getReleaseId(repo, tag, token);

    // Check if already uploaded under this name
    const existing = await hasExistingAsset(repo, releaseId, assetName, token);
    if (existing) {
      await unlink(downloadedPath).catch(() => undefined);
      return NextResponse.json({
        videoUrl: buildProxyAssetUrl(assetName),
        alreadyUploaded: true
      });
    }

    await uploadAsset(repo, releaseId, downloadedPath, assetName, token);
    await unlink(downloadedPath).catch(() => undefined);

    return NextResponse.json({
      videoUrl: buildProxyAssetUrl(assetName),
      alreadyUploaded: false
    });
  } catch (error) {
    if (downloadedPath) await unlink(downloadedPath).catch(() => undefined);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Video download or upload failed.' },
      { status: 400 }
    );
  }
}
