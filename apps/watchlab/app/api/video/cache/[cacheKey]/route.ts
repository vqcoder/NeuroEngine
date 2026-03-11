import { stat } from 'fs/promises';
import { createReadStream } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { Readable } from 'stream';

export const runtime = 'nodejs';

type Context = {
  params: Promise<{ cacheKey: string }>;
};

const VIDEO_CACHE_DIR = path.join(tmpdir(), 'watchlab-video-cache');
const CACHE_KEY_PATTERN = /^[a-f0-9]{24}\.(mp4|webm|ogg|m4v|mov)$/i;

const extensionToContentType: Record<string, string> = {
  mp4: 'video/mp4',
  webm: 'video/webm',
  ogg: 'video/ogg',
  m4v: 'video/x-m4v',
  mov: 'video/quicktime'
};

export async function GET(_request: Request, context: Context) {
  const { cacheKey } = await context.params;
  if (!CACHE_KEY_PATTERN.test(cacheKey)) {
    return new Response('Invalid cache key.', { status: 400 });
  }

  const targetPath = path.join(VIDEO_CACHE_DIR, cacheKey);
  let fileStat;
  try {
    fileStat = await stat(targetPath);
  } catch {
    return new Response('Cached video not found.', { status: 404 });
  }

  const extension = cacheKey.split('.').pop()?.toLowerCase() ?? 'mp4';
  const contentType = extensionToContentType[extension] ?? 'application/octet-stream';
  const webStream = Readable.toWeb(createReadStream(targetPath)) as ReadableStream<Uint8Array>;

  return new Response(webStream, {
    headers: {
      'Content-Type': contentType,
      'Content-Length': String(fileStat.size),
      'Cache-Control': 'public, max-age=31536000, immutable'
    }
  });
}
