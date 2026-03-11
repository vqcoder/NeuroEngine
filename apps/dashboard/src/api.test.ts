import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchVideoSummary,
  fetchVideoCatalog,
  deleteVideo,
  fetchVideoReadout,
  predictVideoFromUrl,
  fetchPredictJobStatus,
  predictVideoFromUrlAwait,
  reportFrontendDiagnostic,
  reportFrontendDiagnosticFireAndForget
} from './api';

// ---------------------------------------------------------------------------
// Shared mocking setup
// ---------------------------------------------------------------------------

/**
 * In the test environment (node mode), `resolveApiBaseCandidates()` falls back
 * to `['http://127.0.0.1:8000']` because there is no `window`. We intercept
 * all fetches to that origin.
 */
const API_BASE = 'http://127.0.0.1:8000';

let mockFetch: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/html' }
  });
}

beforeEach(() => {
  mockFetch = vi.fn();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// fetchVideoSummary
// ---------------------------------------------------------------------------

describe('fetchVideoSummary', () => {
  it('calls the correct endpoint and returns JSON', async () => {
    const summaryPayload = { video_id: 'abc', trace_buckets: [], scene_metrics: [] };
    mockFetch.mockResolvedValueOnce(jsonResponse(summaryPayload));

    const result = await fetchVideoSummary('abc');
    expect(result).toEqual(summaryPayload);
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/videos/abc/summary');
  });

  it('throws on 404 with JSON detail', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Video not found' }, 404));
    await expect(fetchVideoSummary('missing')).rejects.toThrow('Video not found');
  });
});

// ---------------------------------------------------------------------------
// fetchVideoCatalog
// ---------------------------------------------------------------------------

describe('fetchVideoCatalog', () => {
  it('passes default limit=50', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [] }));
    await fetchVideoCatalog();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('limit=50');
  });

  it('passes custom limit parameter', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: [] }));
    await fetchVideoCatalog(10);
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('limit=10');
  });

  it('returns the items array from VideoCatalogResponse', async () => {
    const catalog = [{ video_id: 'a' }, { video_id: 'b' }];
    mockFetch.mockResolvedValueOnce(jsonResponse({ items: catalog }));
    const result = await fetchVideoCatalog();
    expect(result).toEqual(catalog);
  });
});

// ---------------------------------------------------------------------------
// deleteVideo
// ---------------------------------------------------------------------------

describe('deleteVideo', () => {
  it('sends DELETE method', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));
    await deleteVideo('vid1');
    const calledInit = mockFetch.mock.calls[0][1] as RequestInit;
    expect(calledInit.method).toBe('DELETE');
  });

  it('calls the correct endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));
    await deleteVideo('vid1');
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/videos/vid1');
  });
});

// ---------------------------------------------------------------------------
// fetchVideoReadout
// ---------------------------------------------------------------------------

describe('fetchVideoReadout', () => {
  const validReadout = {
    video_id: 'v1',
    traces: { attention_score: [] },
    segments: { attention_gain_segments: [] },
  };

  it('calls the correct endpoint without query params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(validReadout));
    await fetchVideoReadout('v1');
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/videos/v1/readout');
    expect(calledUrl).not.toContain('?');
  });

  it('forwards session_id query param', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(validReadout));
    await fetchVideoReadout('v1', { session_id: 'sess123' });
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('session_id=sess123');
  });

  it('forwards variant_id query param', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(validReadout));
    await fetchVideoReadout('v1', { variant_id: 'var1' });
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('variant_id=var1');
  });

  it('forwards aggregate and window_ms query params', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(validReadout));
    await fetchVideoReadout('v1', { aggregate: true, window_ms: 500 });
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('aggregate=true');
    expect(calledUrl).toContain('window_ms=500');
  });
});

// ---------------------------------------------------------------------------
// predictVideoFromUrl
// ---------------------------------------------------------------------------

describe('predictVideoFromUrl', () => {
  it('sends POST method with FormData', async () => {
    const jobStatus = { job_id: 'j1', status: 'pending' };
    mockFetch.mockResolvedValueOnce(jsonResponse(jobStatus));
    const result = await predictVideoFromUrl('https://example.com/video.mp4');
    expect(result).toEqual(jobStatus);
    const calledInit = mockFetch.mock.calls[0][1] as RequestInit;
    expect(calledInit.method).toBe('POST');
    expect(calledInit.body).toBeInstanceOf(FormData);
  });

  it('sets video_url in FormData', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: 'j1', status: 'pending' }));
    await predictVideoFromUrl('https://example.com/video.mp4');
    const calledInit = mockFetch.mock.calls[0][1] as RequestInit;
    const formData = calledInit.body as FormData;
    expect(formData.get('video_url')).toBe('https://example.com/video.mp4');
  });

  it('calls the /predict endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ job_id: 'j1', status: 'pending' }));
    await predictVideoFromUrl('https://example.com/video.mp4');
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/predict');
  });
});

// ---------------------------------------------------------------------------
// fetchPredictJobStatus
// ---------------------------------------------------------------------------

describe('fetchPredictJobStatus', () => {
  it('calls the correct endpoint by job ID', async () => {
    const status = { job_id: 'j1', status: 'running' };
    mockFetch.mockResolvedValueOnce(jsonResponse(status));
    const result = await fetchPredictJobStatus('j1');
    expect(result).toEqual(status);
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/predict/j1');
  });
});

// ---------------------------------------------------------------------------
// predictVideoFromUrlAwait
// ---------------------------------------------------------------------------

describe('predictVideoFromUrlAwait', () => {
  it('returns result when job completes immediately', async () => {
    const predictions = [{ t_sec: 0, blink_inhibition: 50, dial: 50 }];
    const doneStatus = {
      job_id: 'j1',
      status: 'done',
      result: {
        model_artifact: 'v1',
        predictions,
        resolved_video_url: null,
        prediction_backend: 'test',
        video_id: null
      },
      stage_label: 'done',
      error: null
    };
    // First call: predictVideoFromUrl → POST /predict
    mockFetch.mockResolvedValueOnce(jsonResponse(doneStatus));

    const result = await predictVideoFromUrlAwait('https://example.com/video.mp4', 10, 5000);
    expect(result.predictions).toEqual(predictions);
  });

  it('polls until done', async () => {
    const pendingStatus = {
      job_id: 'j1', status: 'pending', stage_label: 'pending', result: null, error: null
    };
    const doneStatus = {
      job_id: 'j1', status: 'done', stage_label: 'done',
      result: {
        model_artifact: 'v1', predictions: [], resolved_video_url: null,
        prediction_backend: 'test', video_id: null
      },
      error: null
    };
    // First call: POST /predict → pending
    mockFetch.mockResolvedValueOnce(jsonResponse(pendingStatus));
    // Second call: GET /predict/j1 → done
    mockFetch.mockResolvedValueOnce(jsonResponse(doneStatus));

    const result = await predictVideoFromUrlAwait('https://example.com/video.mp4', 10, 30000);
    expect(result.predictions).toEqual([]);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('throws on failed job', async () => {
    const failedStatus = {
      job_id: 'j1', status: 'failed', stage_label: 'failed',
      result: null, error: 'GPU out of memory'
    };
    mockFetch.mockResolvedValueOnce(jsonResponse(failedStatus));
    await expect(
      predictVideoFromUrlAwait('https://example.com/video.mp4', 10, 5000)
    ).rejects.toThrow('GPU out of memory');
  });

  it('throws on timeout', async () => {
    const pendingStatus = {
      job_id: 'j1', status: 'running', stage_label: 'running', result: null, error: null
    };
    // Return a fresh Response each call to avoid "body already read" errors
    mockFetch.mockImplementation(() =>
      Promise.resolve(jsonResponse(pendingStatus))
    );

    await expect(
      predictVideoFromUrlAwait('https://example.com/video.mp4', 5, 20)
    ).rejects.toThrow(/timed out/i);
  });
});

// ---------------------------------------------------------------------------
// reportFrontendDiagnostic
// ---------------------------------------------------------------------------

describe('reportFrontendDiagnostic', () => {
  it('sends POST with JSON body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));
    const payload: import('./types').FrontendDiagnosticEventInput = {
      event_type: 'error',
      surface: 'dashboard',
      page: 'readout',
      severity: 'warning',
      message: 'Test error'
    };
    await reportFrontendDiagnostic(payload);

    const calledInit = mockFetch.mock.calls[0][1] as RequestInit;
    expect(calledInit.method).toBe('POST');
    expect(calledInit.headers).toEqual(
      expect.objectContaining({ 'Content-Type': 'application/json' })
    );
    const body = JSON.parse(calledInit.body as string);
    expect(body.event_type).toBe('error');
    expect(body.message).toBe('Test error');
  });

  it('calls the diagnostics endpoint', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ok: true }));
    const payload: import('./types').FrontendDiagnosticEventInput = {
      event_type: 'info',
      surface: 'dashboard',
      page: 'unknown',
      severity: 'info'
    };
    await reportFrontendDiagnostic(payload);
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain('/observability/frontend-diagnostics/events');
  });
});

// ---------------------------------------------------------------------------
// reportFrontendDiagnosticFireAndForget
// ---------------------------------------------------------------------------

describe('reportFrontendDiagnosticFireAndForget', () => {
  it('does not throw even when fetch fails', () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    // Should not throw
    expect(() => {
      reportFrontendDiagnosticFireAndForget({
        event_type: 'error',
        surface: 'dashboard',
        page: 'unknown',
        severity: 'error'
      });
    }).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Retry / fallback behavior
// ---------------------------------------------------------------------------

describe('fetchApi retry/fallback behavior', () => {
  it('throws for non-JSON successful response on single candidate', async () => {
    mockFetch.mockResolvedValueOnce(textResponse('<html>Not an API</html>'));
    await expect(fetchVideoSummary('abc')).rejects.toThrow(/non-JSON|Failed to fetch/i);
  });

  it('throws immediately for 4xx JSON errors (no fallback)', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Not authorized' }, 401));
    await expect(fetchVideoSummary('abc')).rejects.toThrow('Not authorized');
    // Should not retry
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('extracts detail from error JSON body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Video not found' }, 404));
    await expect(fetchVideoSummary('missing')).rejects.toThrow('Video not found');
  });

  it('extracts message from error JSON body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ message: 'Bad request' }, 400));
    await expect(fetchVideoSummary('bad')).rejects.toThrow('Bad request');
  });

  it('extracts error field from error JSON body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ error: 'Something broke' }, 422));
    await expect(fetchVideoSummary('broken')).rejects.toThrow('Something broke');
  });
});

// ---------------------------------------------------------------------------
// Transient retry behavior (502, 503, 429, network errors)
// ---------------------------------------------------------------------------

describe('transient retry behavior', () => {
  it('retries on 503 then succeeds', async () => {
    const summaryPayload = { video_id: 'abc', trace_buckets: [], scene_metrics: [] };
    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve(
          new Response('Service Unavailable', { status: 503, headers: { 'Content-Type': 'text/plain' } })
        );
      }
      return Promise.resolve(jsonResponse(summaryPayload));
    });

    const result = await fetchVideoSummary('abc');
    expect(result).toEqual(summaryPayload);
    // At least 2 calls: one 503 + one success. Module-level rememberedApiBaseUrl
    // from prior tests may cause an extra candidate attempt.
    expect(callCount).toBeGreaterThanOrEqual(2);
  });

  it('retries on 502 then succeeds', async () => {
    const summaryPayload = { video_id: 'abc', trace_buckets: [], scene_metrics: [] };
    mockFetch.mockResolvedValueOnce(
      new Response('Bad Gateway', { status: 502, headers: { 'Content-Type': 'text/plain' } })
    );
    mockFetch.mockResolvedValueOnce(jsonResponse(summaryPayload));

    const result = await fetchVideoSummary('abc');
    expect(result).toEqual(summaryPayload);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('retries on 429 then succeeds', async () => {
    const summaryPayload = { video_id: 'abc', trace_buckets: [], scene_metrics: [] };
    mockFetch.mockResolvedValueOnce(
      new Response('Too Many Requests', { status: 429, headers: { 'Content-Type': 'text/plain' } })
    );
    mockFetch.mockResolvedValueOnce(jsonResponse(summaryPayload));

    const result = await fetchVideoSummary('abc');
    expect(result).toEqual(summaryPayload);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('retries on network error (TypeError) then succeeds', async () => {
    const summaryPayload = { video_id: 'abc', trace_buckets: [], scene_metrics: [] };
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    mockFetch.mockResolvedValueOnce(jsonResponse(summaryPayload));

    const result = await fetchVideoSummary('abc');
    expect(result).toEqual(summaryPayload);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('exhausts retries on repeated 503 and throws', async () => {
    // 3 attempts total (1 + 2 retries), all 503
    mockFetch.mockImplementation(() =>
      Promise.resolve(new Response('Service Unavailable', { status: 503, headers: { 'Content-Type': 'text/plain' } }))
    );

    await expect(fetchVideoSummary('abc')).rejects.toThrow(/503|Failed to fetch/);
    // 1 initial + 2 retries = 3
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it('does NOT retry on 500 (non-transient server error)', async () => {
    mockFetch.mockResolvedValueOnce(
      new Response('Internal Server Error', { status: 500, headers: { 'Content-Type': 'text/plain' } })
    );

    await expect(fetchVideoSummary('abc')).rejects.toThrow(/500|Failed to fetch/);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('does NOT retry on 4xx JSON errors', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: 'Not found' }, 404));

    await expect(fetchVideoSummary('missing')).rejects.toThrow('Not found');
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// Response shape guard integration
// ---------------------------------------------------------------------------

describe('response shape guards', () => {
  it('fetchVideoCatalog rejects non-object response', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([{ video_id: 'a' }]));
    await expect(fetchVideoCatalog()).rejects.toThrow(/expected object, got array/);
  });

  it('fetchVideoCatalog rejects missing items field', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ data: [] }));
    await expect(fetchVideoCatalog()).rejects.toThrow(/missing required field "items"/);
  });

  it('fetchVideoReadout rejects missing traces field', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ video_id: 'v1', segments: { attention_gain_segments: [] } })
    );
    await expect(fetchVideoReadout('v1')).rejects.toThrow(/missing required field "traces"/);
  });

  it('fetchVideoSummary rejects null body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(null));
    await expect(fetchVideoSummary('abc')).rejects.toThrow(/expected object, got null/);
  });
});
