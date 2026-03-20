import type {
  AnalystSessionsResponse,
  CaptureArchiveObservabilityStatus,
  FrontendDiagnosticEventInput,
  FrontendDiagnosticEventsResponse,
  FrontendDiagnosticSummary,
  NeuroObservabilityStatus,
  PredictJobsObservabilityStatus,
  PredictJobStatus,
  PredictResponse,
  ReadoutExportPackage,
  StudyDetail,
  StudyListItem,
  VideoCatalogItem,
  VideoCatalogResponse,
  VideoReadout,
  VideoSummary
} from './types';
import { guardIsObject, guardItemsWrapper, guardReadoutShape } from './api-guards';

const DEFAULT_LOCAL_API_BASE_URL = 'http://127.0.0.1:8000';
const DEFAULT_PROD_API_BASE_URLS: string[] = (
  import.meta.env.VITE_PROD_API_BASE_URLS
    ? String(import.meta.env.VITE_PROD_API_BASE_URLS).split(',').map((u: string) => u.trim()).filter(Boolean)
    : []
);
const API_BASE_STORAGE_KEY = 'neurotrace_api_base_url';

/**
 * In production the API token is injected server-side by server.mjs through
 * the /api-proxy/ reverse proxy — the client never sees it.
 *
 * VITE_API_TOKEN is kept as a legacy fallback for local dev only; it is NOT
 * set in the production Dockerfile so it will be empty in production builds.
 */
const _LEGACY_API_TOKEN = (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim() ?? '';

function withAuth(init?: RequestInit): RequestInit {
  if (!_LEGACY_API_TOKEN) return init ?? {};
  const existing = (init?.headers ?? {}) as Record<string, string>;
  return { ...init, headers: { Authorization: `Bearer ${_LEGACY_API_TOKEN}`, ...existing } };
}

/**
 * The server-side API proxy prefix. In production, server.mjs exposes this
 * path and forwards requests to the biograph API with the auth token injected.
 */
const API_PROXY_PREFIX = '/api-proxy';

function isLocalHostname(hostname: string): boolean {
  const normalized = hostname.trim().toLowerCase();
  return (
    normalized === 'localhost' ||
    normalized === '127.0.0.1' ||
    normalized === '0.0.0.0' ||
    normalized.endsWith('.local')
  );
}

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, '');
}

/**
 * Security: only accept API base URLs that match known trusted domains.
 * Prevents token exfiltration via crafted `?api_base_url=https://attacker.com` links.
 */
function isAllowedApiBaseUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    const hostname = parsed.hostname.toLowerCase();

    // Localhost / local dev
    if (isLocalHostname(hostname)) return true;

    // Same origin
    if (typeof window !== 'undefined' && hostname === window.location.hostname.toLowerCase()) {
      return true;
    }

    // Railway deployments
    if (hostname.endsWith('.railway.app')) return true;

    // Production domain
    if (hostname.endsWith('.alpha-engine.ai')) return true;

    // Explicitly configured production URLs
    if (
      DEFAULT_PROD_API_BASE_URLS.some((allowed) => {
        try {
          return new URL(allowed).hostname.toLowerCase() === hostname;
        } catch {
          return false;
        }
      })
    ) {
      return true;
    }

    return false;
  } catch {
    return false;
  }
}

function deriveRailwayApiBaseFromDashboardHost(hostname: string): string[] {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized.endsWith('.railway.app')) {
    return [];
  }

  const candidates = new Set<string>();
  if (normalized.includes('dashboard')) {
    candidates.add(`https://${normalized.replace(/dashboard/g, 'biograph-api')}`);
  }
  if (normalized.includes('watchlab')) {
    candidates.add(`https://${normalized.replace(/watchlab/g, 'biograph-api')}`);
  }

  const [subdomain, ...suffix] = normalized.split('.');
  if (subdomain && suffix.length > 0) {
    candidates.add(`https://${['biograph-api', ...suffix].join('.')}`);

    const productionMatch = subdomain.match(/^(?:.+)-production-([a-z0-9]+)$/);
    if (productionMatch?.[1]) {
      candidates.add(`https://biograph-api-production-${productionMatch[1]}.${suffix.join('.')}`);
    }
  }

  DEFAULT_PROD_API_BASE_URLS.forEach((value) => candidates.add(value));
  return [...candidates];
}

function resolveApiBaseCandidates(): string[] {
  const candidates = new Set<string>();

  // In production, prefer the server-side proxy which injects the auth token.
  // The proxy is served at the same origin under /api-proxy/.
  if (typeof window !== 'undefined' && !isLocalHostname(window.location.hostname)) {
    candidates.add(`${normalizeBaseUrl(window.location.origin)}${API_PROXY_PREFIX}`);
  }

  const fromEnv = import.meta.env.VITE_API_BASE_URL?.trim();
  if (fromEnv) {
    candidates.add(normalizeBaseUrl(fromEnv));
  }

  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    const searchValue = new URLSearchParams(window.location.search).get('api_base_url')?.trim();
    if (searchValue) {
      const normalized = normalizeBaseUrl(searchValue);
      if (isAllowedApiBaseUrl(normalized)) {
        candidates.add(normalized);
        try {
          window.localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
        } catch {
          // Ignore storage errors (private mode or blocked storage).
        }
      } else {
        console.warn(
          `[neurotrace] Ignoring untrusted api_base_url: ${searchValue}. ` +
            'Only localhost, *.railway.app, and *.alpha-engine.ai are allowed.'
        );
      }
    }

    try {
      const stored = window.localStorage.getItem(API_BASE_STORAGE_KEY)?.trim();
      if (stored) {
        const normalizedStored = normalizeBaseUrl(stored);
        if (isAllowedApiBaseUrl(normalizedStored)) {
          candidates.add(normalizedStored);
        } else {
          // Clear stale untrusted URL from localStorage.
          window.localStorage.removeItem(API_BASE_STORAGE_KEY);
        }
      }
    } catch {
      // Ignore storage read errors.
    }

    if (isLocalHostname(hostname)) {
      candidates.add(DEFAULT_LOCAL_API_BASE_URL);
    } else {
      candidates.add(normalizeBaseUrl(window.location.origin));
      deriveRailwayApiBaseFromDashboardHost(hostname).forEach((baseUrl) =>
        candidates.add(normalizeBaseUrl(baseUrl))
      );
      DEFAULT_PROD_API_BASE_URLS.forEach((baseUrl) => candidates.add(normalizeBaseUrl(baseUrl)));
    }
  }

  if (candidates.size === 0) {
    candidates.add(DEFAULT_LOCAL_API_BASE_URL);
  }
  return [...candidates];
}

let rememberedApiBaseUrl: string | null = null;

/** Per-attempt fetch timeout. Prevents indefinite hangs on unresponsive servers. */
const FETCH_TIMEOUT_MS = 30_000;

/** Max retries for transient errors (502, 503, 429, network) on the same base URL. */
const TRANSIENT_MAX_RETRIES = 2;
/** Base delay between transient retries — multiplied by attempt number. */
const TRANSIENT_RETRY_DELAY_MS = 1500;

function isJsonContentType(contentType: string | null): boolean {
  if (!contentType) {
    return false;
  }
  const normalized = contentType.toLowerCase();
  return (
    normalized.includes('application/json') ||
    normalized.includes('+json') ||
    normalized.includes('text/json')
  );
}

function isTransientStatus(status: number): boolean {
  return status === 502 || status === 503 || status === 429;
}

async function fetchApi(pathWithQuery: string, init?: RequestInit): Promise<Response> {
  init = withAuth(init);
  const candidates = resolveApiBaseCandidates();
  if (rememberedApiBaseUrl) {
    const index = candidates.indexOf(rememberedApiBaseUrl);
    if (index > 0) {
      candidates.splice(index, 1);
      candidates.unshift(rememberedApiBaseUrl);
    } else if (index < 0) {
      candidates.unshift(rememberedApiBaseUrl);
    }
  }

  const attempts: string[] = [];
  let lastError: Error | null = null;

  for (const baseUrl of candidates) {
    const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
    const url = `${normalizedBaseUrl}${pathWithQuery}`;
    attempts.push(url);

    // Inner retry loop: retry transient errors (502, 503, 429, network) on
    // the same base URL before falling through to the next candidate.
    let movedToNextCandidate = false;
    for (let retry = 0; retry <= TRANSIENT_MAX_RETRIES; retry++) {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

      let response: Response;
      try {
        response = await fetch(url, { ...init, signal: controller.signal });
      } catch (error) {
        clearTimeout(timeoutId);
        if (error instanceof DOMException && error.name === 'AbortError') {
          lastError = new Error(`Request to ${normalizedBaseUrl} timed out after ${FETCH_TIMEOUT_MS / 1000}s`);
        } else {
          lastError = error instanceof Error ? error : new Error('Failed to fetch');
        }
        // Network errors are transient — retry if attempts remain
        if (retry < TRANSIENT_MAX_RETRIES) {
          await new Promise((r) => setTimeout(r, TRANSIENT_RETRY_DELAY_MS * (retry + 1)));
          continue;
        }
        movedToNextCandidate = true;
        break;
      }
      clearTimeout(timeoutId);

      const contentType = response.headers.get('content-type');

      if (!response.ok) {
        // 4xx with a JSON body = the right API host responding with a business error.
        // Surface the detail immediately — no retry, no fallthrough.
        if (response.status >= 400 && response.status < 500 && isJsonContentType(contentType)) {
          let detail = `HTTP ${response.status}`;
          try {
            const body = await response.json() as Record<string, unknown>;
            if (typeof body.detail === 'string') {
              detail = body.detail;
            } else if (typeof body.message === 'string') {
              detail = body.message;
            } else if (typeof body.error === 'string') {
              detail = body.error;
            }
          } catch {
            // fall through with generic detail
          }
          throw new Error(detail);
        }

        // Transient error → retry same URL
        if (isTransientStatus(response.status) && retry < TRANSIENT_MAX_RETRIES) {
          lastError = new Error(`HTTP ${response.status}`);
          await new Promise((r) => setTimeout(r, TRANSIENT_RETRY_DELAY_MS * (retry + 1)));
          continue;
        }

        // Non-transient or retries exhausted → try next candidate
        lastError = new Error(`HTTP ${response.status}`);
        movedToNextCandidate = true;
        break;
      }

      if (!isJsonContentType(contentType)) {
        const preview = (await response.clone().text()).slice(0, 120).replace(/\s+/g, ' ').trim();
        lastError = new Error(
          `Unexpected non-JSON response from ${normalizedBaseUrl}: ${preview || 'empty response body'}`
        );
        movedToNextCandidate = true;
        break;
      }

      // Success
      rememberedApiBaseUrl = normalizedBaseUrl;
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(API_BASE_STORAGE_KEY, normalizedBaseUrl);
        }
      } catch {
        // Ignore storage write errors.
      }
      return response;
    }

    if (movedToNextCandidate) {
      continue;
    }
  }

  const detail = lastError ? ` Last error: ${lastError.message}.` : '';
  throw new Error(
    `Failed to fetch API.${detail} Tried: ${attempts.join(
      ', '
    )}. If this is a cloud deploy, set VITE_API_BASE_URL or pass ?api_base_url=<api-domain>.`
  );
}

export async function fetchVideoSummary(videoId: string): Promise<VideoSummary> {
  const response = await fetchApi(`/videos/${videoId}/summary`);
  const body = await response.json();
  guardIsObject(body, `GET /videos/${videoId}/summary`);
  return body as VideoSummary;
}

export type VideoReadoutQuery = {
  session_id?: string;
  variant_id?: string;
  aggregate?: boolean;
  window_ms?: number;
};

export async function fetchVideoCatalog(limit = 50): Promise<VideoCatalogItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetchApi(`/videos?${params.toString()}`);
  const body = await response.json();
  return guardItemsWrapper(body, 'GET /videos') as VideoCatalogItem[];
}

export async function deleteVideo(videoId: string): Promise<void> {
  await fetchApi(`/videos/${videoId}`, { method: 'DELETE' });
}

export async function fetchVideoReadout(
  videoId: string,
  query: VideoReadoutQuery = {}
): Promise<VideoReadout> {
  const params = new URLSearchParams();
  if (query.session_id) {
    params.set('session_id', query.session_id);
  }
  if (query.variant_id) {
    params.set('variant_id', query.variant_id);
  }
  if (query.aggregate !== undefined) {
    params.set('aggregate', String(query.aggregate));
  }
  if (query.window_ms !== undefined) {
    params.set('window_ms', String(query.window_ms));
  }

  const suffix = params.toString();
  const endpoint = `/videos/${videoId}/readout${suffix ? `?${suffix}` : ''}`;
  const response = await fetchApi(endpoint);
  const body = await response.json();
  guardReadoutShape(body, `GET ${endpoint}`);
  return body as VideoReadout;
}

export async function fetchVideoReadoutExportPackage(
  videoId: string,
  query: VideoReadoutQuery = {}
): Promise<ReadoutExportPackage> {
  const params = new URLSearchParams();
  if (query.session_id) {
    params.set('session_id', query.session_id);
  }
  if (query.variant_id) {
    params.set('variant_id', query.variant_id);
  }
  if (query.aggregate !== undefined) {
    params.set('aggregate', String(query.aggregate));
  }
  if (query.window_ms !== undefined) {
    params.set('window_ms', String(query.window_ms));
  }

  const suffix = params.toString();
  const endpoint = `/videos/${videoId}/readout/export-package${suffix ? `?${suffix}` : ''}`;
  const response = await fetchApi(endpoint);
  const body = await response.json();
  guardIsObject(body, `GET ${endpoint}`);
  return body as ReadoutExportPackage;
}

export async function predictVideoFromUrl(videoUrl: string): Promise<PredictJobStatus> {
  const formData = new FormData();
  formData.set('video_url', videoUrl);

  const response = await fetchApi('/predict', {
    method: 'POST',
    body: formData
  });
  return (await response.json()) as PredictJobStatus;
}

export async function predictVideoFromFile(file: File): Promise<PredictJobStatus> {
  const formData = new FormData();
  formData.set('file', file, file.name);

  const response = await fetchApi('/predict', {
    method: 'POST',
    body: formData
  });
  return (await response.json()) as PredictJobStatus;
}

export async function fetchPredictJobStatus(jobId: string): Promise<PredictJobStatus> {
  const response = await fetchApi(`/predict/${jobId}`);
  const body = await response.json();
  guardIsObject(body, `GET /predict/${jobId}`);
  return body as PredictJobStatus;
}

export async function fetchPredictJobsObservabilityStatus(): Promise<PredictJobsObservabilityStatus> {
  const response = await fetchApi('/observability/predict-jobs');
  return (await response.json()) as PredictJobsObservabilityStatus;
}

/** Poll until the job reaches a terminal state and return the result, or throw on failure. */
export async function predictVideoFromUrlAwait(
  videoUrl: string,
  pollIntervalMs = 2000,
  maxTimeoutMs = 600_000 // 10 minutes
): Promise<PredictResponse> {
  const deadline = Date.now() + maxTimeoutMs;
  let status = await predictVideoFromUrl(videoUrl);
  while (status.status !== 'done' && status.status !== 'failed') {
    if (Date.now() > deadline) {
      throw new Error(`Prediction timed out after ${maxTimeoutMs / 1000}s (job ${status.job_id})`);
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    status = await fetchPredictJobStatus(status.job_id);
  }
  if (status.status === 'failed' || !status.result) {
    throw new Error(status.error ?? 'Prediction failed.');
  }
  return status.result;
}

export async function fetchNeuroObservabilityStatus(): Promise<NeuroObservabilityStatus> {
  const response = await fetchApi('/observability/neuro');
  return (await response.json()) as NeuroObservabilityStatus;
}

export async function fetchCaptureArchiveObservabilityStatus(): Promise<CaptureArchiveObservabilityStatus> {
  const response = await fetchApi('/observability/capture-archives');
  return (await response.json()) as CaptureArchiveObservabilityStatus;
}

export async function reportFrontendDiagnostic(
  payload: FrontendDiagnosticEventInput
): Promise<void> {
  const response = await fetchApi('/observability/frontend-diagnostics/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  await response.json().catch(() => null);
}

export function reportFrontendDiagnosticFireAndForget(
  payload: FrontendDiagnosticEventInput
): void {
  void reportFrontendDiagnostic(payload).catch(() => undefined);
}

export async function fetchFrontendDiagnosticsSummary(
  windowHours = 24,
  topN = 8
): Promise<FrontendDiagnosticSummary> {
  const params = new URLSearchParams();
  params.set('window_hours', String(windowHours));
  params.set('top_n', String(topN));
  const response = await fetchApi(`/observability/frontend-diagnostics/summary?${params.toString()}`);
  return (await response.json()) as FrontendDiagnosticSummary;
}

export type FrontendDiagnosticEventsQuery = {
  limit?: number;
  surface?: string;
  page?: string;
  severity?: string;
  event_type?: string;
};

export async function fetchFrontendDiagnosticEvents(
  query: FrontendDiagnosticEventsQuery = {}
): Promise<FrontendDiagnosticEventsResponse> {
  const params = new URLSearchParams();
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit));
  }
  if (query.surface) {
    params.set('surface', query.surface);
  }
  if (query.page) {
    params.set('page', query.page);
  }
  if (query.severity) {
    params.set('severity', query.severity);
  }
  if (query.event_type) {
    params.set('event_type', query.event_type);
  }

  const suffix = params.toString();
  const response = await fetchApi(
    `/observability/frontend-diagnostics/events${suffix ? `?${suffix}` : ''}`
  );
  return (await response.json()) as FrontendDiagnosticEventsResponse;
}

// ---------------------------------------------------------------------------
// Analyst View
// ---------------------------------------------------------------------------

export async function fetchAnalystSessions(
  videoId: string
): Promise<AnalystSessionsResponse> {
  const response = await fetchApi(`/analyst/videos/${videoId}/sessions`);
  return (await response.json()) as AnalystSessionsResponse;
}

// ---------------------------------------------------------------------------
// Study Management
// ---------------------------------------------------------------------------

export async function fetchStudies(limit = 50): Promise<StudyListItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetchApi(`/studies?${params.toString()}`);
  const body = await response.json();
  return guardItemsWrapper(body, 'GET /studies') as StudyListItem[];
}

export async function fetchStudyDetail(studyId: string): Promise<StudyDetail> {
  const response = await fetchApi(`/studies/${studyId}`);
  const body = await response.json();
  guardIsObject(body, `GET /studies/${studyId}`);
  return body as StudyDetail;
}

export async function createStudy(name: string, description?: string): Promise<StudyListItem> {
  const response = await fetchApi('/studies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  });
  const body = await response.json();
  guardIsObject(body, 'POST /studies');
  return body as StudyListItem;
}

export async function updateStudy(studyId: string, updates: { name?: string; description?: string }): Promise<StudyListItem> {
  const response = await fetchApi(`/studies/${studyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  const body = await response.json();
  guardIsObject(body, `PATCH /studies/${studyId}`);
  return body as StudyListItem;
}

export async function deleteStudy(studyId: string): Promise<void> {
  await fetchApi(`/studies/${studyId}`, { method: 'DELETE' });
}
