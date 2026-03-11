// ---------------------------------------------------------------------------
// Minimal production server for the dashboard SPA.
//
// Replaces the plain `serve` static-file server to add a reverse-proxy path
// at /api-proxy/* that forwards requests to the biograph API with an
// Authorization header injected server-side.  This keeps the API token out
// of the client JS bundle (fixes S7 — VITE_API_TOKEN in browser bundle).
//
// Env vars (runtime, NOT build-time):
//   API_TOKEN          — Bearer token for the biograph API (server-only)
//   API_BASE_URL       — biograph API origin (e.g. https://biograph-api-production.up.railway.app)
//   PORT               — listen port (default 4173)
// ---------------------------------------------------------------------------

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const DIST_DIR = join(__dirname, 'dist');
const PORT = Number(process.env.PORT) || 4173;
const API_TOKEN = process.env.API_TOKEN?.trim() || '';
const API_BASE_URL = (process.env.API_BASE_URL?.trim() || '').replace(/\/+$/, '');

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json',
  '.webp': 'image/webp',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
  '.txt': 'text/plain; charset=utf-8',
};

// ── Static file serving ──────────────────────────────────────────────────

async function serveStatic(req, res) {
  let pathname = new URL(req.url, `http://localhost:${PORT}`).pathname;
  if (pathname === '/') pathname = '/index.html';

  const filePath = join(DIST_DIR, pathname);

  // Prevent directory traversal
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  try {
    const info = await stat(filePath);
    if (info.isFile()) {
      const ext = extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || 'application/octet-stream';
      const content = await readFile(filePath);

      // Cache assets with hashed filenames aggressively
      const cacheControl = pathname.includes('/assets/')
        ? 'public, max-age=31536000, immutable'
        : 'public, max-age=0, must-revalidate';

      res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': content.byteLength,
        'Cache-Control': cacheControl,
      });
      res.end(content);
      return;
    }
  } catch {
    // Fall through to SPA fallback
  }

  // SPA fallback — serve index.html for client-side routing
  try {
    const indexPath = join(DIST_DIR, 'index.html');
    const content = await readFile(indexPath);
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'public, max-age=0, must-revalidate',
    });
    res.end(content);
  } catch {
    res.writeHead(500);
    res.end('Internal Server Error');
  }
}

// ── API Proxy ────────────────────────────────────────────────────────────

const API_PROXY_PREFIX = '/api-proxy/';

async function proxyApiRequest(req, res) {
  if (!API_BASE_URL) {
    res.writeHead(503, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'API_BASE_URL not configured on server.' }));
    return;
  }

  const targetPath = req.url.slice(API_PROXY_PREFIX.length - 1); // keep leading /
  const targetUrl = `${API_BASE_URL}${targetPath}`;

  // Collect request body
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const body = chunks.length > 0 ? Buffer.concat(chunks) : undefined;

  // Forward headers, injecting Authorization
  const forwardHeaders = {};
  for (const [key, value] of Object.entries(req.headers)) {
    const lower = key.toLowerCase();
    // Skip hop-by-hop and host headers
    if (['host', 'connection', 'keep-alive', 'transfer-encoding'].includes(lower)) continue;
    forwardHeaders[key] = value;
  }
  if (API_TOKEN) {
    forwardHeaders['Authorization'] = `Bearer ${API_TOKEN}`;
  }

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: forwardHeaders,
      body: body && body.byteLength > 0 ? body : undefined,
      redirect: 'follow',
    });

    // Forward response headers
    const responseHeaders = {};
    upstream.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (!['transfer-encoding', 'connection'].includes(lower)) {
        responseHeaders[key] = value;
      }
    });
    // Add CORS for same-origin requests
    responseHeaders['Access-Control-Allow-Origin'] = '*';

    const responseBody = await upstream.arrayBuffer();
    res.writeHead(upstream.status, responseHeaders);
    res.end(Buffer.from(responseBody));
  } catch (error) {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      error: `Proxy error: ${error instanceof Error ? error.message : 'unknown'}`
    }));
  }
}

// Handle CORS preflight for the proxy
function handleCorsPreflightProxy(req, res) {
  res.writeHead(204, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Accept',
    'Access-Control-Max-Age': '86400',
  });
  res.end();
}

// ── Server ───────────────────────────────────────────────────────────────

const server = createServer(async (req, res) => {
  try {
    if (req.url.startsWith(API_PROXY_PREFIX)) {
      if (req.method === 'OPTIONS') {
        handleCorsPreflightProxy(req, res);
      } else {
        await proxyApiRequest(req, res);
      }
    } else {
      await serveStatic(req, res);
    }
  } catch (error) {
    console.error('Unhandled server error:', error);
    if (!res.headersSent) {
      res.writeHead(500);
      res.end('Internal Server Error');
    }
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Dashboard server listening on http://0.0.0.0:${PORT}`);
  if (API_BASE_URL) {
    console.log(`API proxy: /api-proxy/* → ${API_BASE_URL}/* (token: ${API_TOKEN ? 'configured' : 'NOT SET'})`);
  } else {
    console.log('API proxy: DISABLED (API_BASE_URL not set)');
  }
});
