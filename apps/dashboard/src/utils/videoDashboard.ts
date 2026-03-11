/**
 * Pure utility functions for the Video Dashboard page.
 * No React dependencies — safe to use in tests and workers.
 */

import type { PredictTracePoint, ReadoutTimelinePoint } from '../types';

export const SAMPLE_VIDEO_URL = '/sample.mp4';
export const DEFAULT_WINDOW_MS = 1000;
export const VIDEO_ASSET_PROXY_PATH = '/api/video-assets/';
export const VIDEO_ASSET_PUBLIC_PATH = '/video-assets/';
export const VIDEO_HLS_PROXY_PATH = '/api/video/hls-proxy';
export const LEGACY_VIDEO_ASSET_ORIGIN =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') ?? '';
export const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function asUuidOrUndefined(value: string | null | undefined): string | undefined {
  if (!value) {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return UUID_PATTERN.test(trimmed) ? trimmed : undefined;
}

export function createBlankTimelinePoint(tMs: number): ReadoutTimelinePoint {
  return {
    tMs,
    tSec: tMs / 1000,
    sceneId: null,
    cutId: null,
    ctaId: null,
    attentionScore: null,
    attentionVelocity: null,
    blinkRate: null,
    blinkInhibition: null,
    rewardProxy: null,
    valenceProxy: null,
    arousalProxy: null,
    noveltyProxy: null,
    trackingConfidence: null,
    auValues: {}
  };
}

export function mergeMeasuredAndPredictedTimeline(
  measured: ReadoutTimelinePoint[],
  predicted: PredictTracePoint[]
): ReadoutTimelinePoint[] {
  if (predicted.length === 0) {
    return measured;
  }

  const rowsByMs = new Map<number, ReadoutTimelinePoint>();
  measured.forEach((point) => {
    rowsByMs.set(point.tMs, { ...point, auValues: { ...point.auValues } });
  });

  predicted.forEach((prediction) => {
    const tMs = Math.max(0, Math.round(prediction.t_sec * 1000));
    const row = rowsByMs.get(tMs) ?? createBlankTimelinePoint(tMs);
    row.predictedAttentionScore = prediction.attention;
    row.predictedRewardProxy = prediction.reward_proxy ?? null;
    row.predictedBlinkInhibition = prediction.blink_inhibition;
    rowsByMs.set(tMs, row);
  });

  return [...rowsByMs.values()].sort((a, b) => a.tMs - b.tMs);
}

export function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function normalizeLegacyAssetProxyUrl(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith(VIDEO_ASSET_PROXY_PATH)) {
    const remainder = trimmed.slice(VIDEO_ASSET_PROXY_PATH.length);
    if (!remainder) {
      return trimmed;
    }
    return `${LEGACY_VIDEO_ASSET_ORIGIN}/video-assets/${remainder}`;
  }
  if (trimmed.startsWith(VIDEO_ASSET_PUBLIC_PATH)) {
    const remainder = trimmed.slice(VIDEO_ASSET_PUBLIC_PATH.length);
    if (!remainder) {
      return trimmed;
    }
    return `${LEGACY_VIDEO_ASSET_ORIGIN}/video-assets/${remainder}`;
  }
  try {
    const parsed = new URL(trimmed);
    const pathname = parsed.pathname;
    if (pathname.startsWith(VIDEO_ASSET_PROXY_PATH)) {
      const remainder = pathname.slice(VIDEO_ASSET_PROXY_PATH.length);
      if (!remainder) {
        return trimmed;
      }
      return `${LEGACY_VIDEO_ASSET_ORIGIN}/video-assets/${remainder}${parsed.search}${parsed.hash}`;
    }
    if (pathname.startsWith(VIDEO_ASSET_PUBLIC_PATH)) {
      const remainder = pathname.slice(VIDEO_ASSET_PUBLIC_PATH.length);
      if (!remainder) {
        return trimmed;
      }
      return `${LEGACY_VIDEO_ASSET_ORIGIN}/video-assets/${remainder}${parsed.search}${parsed.hash}`;
    }
  } catch {
    return trimmed;
  }
  return trimmed;
}

export function unwrapHlsProxySourceUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    const parsed =
      trimmed.startsWith('http://') || trimmed.startsWith('https://')
        ? new URL(trimmed)
        : new URL(trimmed, 'https://dashboard.local');
    if (!parsed.pathname.startsWith(VIDEO_HLS_PROXY_PATH)) {
      return null;
    }
    const proxied = parsed.searchParams.get('url')?.trim() ?? '';
    return proxied || null;
  } catch {
    return null;
  }
}

export function buildVideoSourceCandidates(sourceUrl: string | null | undefined): string[] {
  const trimmed = sourceUrl?.trim() ?? '';
  const candidates: string[] = [];
  if (trimmed) {
    const unwrapped = unwrapHlsProxySourceUrl(trimmed);
    const rawCandidates = [trimmed, ...(unwrapped ? [unwrapped] : [])];
    for (const candidate of rawCandidates) {
      candidates.push(candidate);
      const legacySource = normalizeLegacyAssetProxyUrl(candidate);
      if (legacySource !== candidate) {
        candidates.push(legacySource);
      }
    }
  }
  candidates.push(SAMPLE_VIDEO_URL);
  return [...new Set(candidates.filter((candidate) => candidate.length > 0))];
}

export function resolvePredictionSourceUrl(
  sourceUrl: string | null | undefined,
  fallbackCandidates: string[]
): string | null {
  const candidates = [
    ...(sourceUrl ? [sourceUrl] : []),
    ...fallbackCandidates
  ].map((candidate) => candidate.trim());

  for (const candidate of candidates) {
    if (isHttpUrl(candidate)) {
      return candidate;
    }
  }

  const relativeCandidate = candidates.find((candidate) => candidate.startsWith('/'));
  if (relativeCandidate && typeof window !== 'undefined') {
    return `${window.location.origin}${relativeCandidate}`;
  }

  return null;
}

// ── Format helpers ──────────────────────────────────────────────────

export const formatSurveyScore = (value: number | null | undefined): string =>
  value === null || value === undefined ? 'n/a' : value.toFixed(2);

export const formatSynchrony = (value: number | null | undefined): string =>
  value === null || value === undefined ? 'n/a' : value.toFixed(3);

export const formatIndexScore = (value: number | null | undefined): string =>
  value === null || value === undefined ? 'n/a' : value.toFixed(1);

export const formatConfidence = (value: number | null | undefined): string =>
  value === null || value === undefined ? 'n/a' : `${Math.round(value * 100)}%`;

export function formatSynchronyPathway(pathway: string | null | undefined): string {
  switch (pathway) {
    case 'direct_panel_gaze':
      return 'Direct panel gaze';
    case 'fallback_proxy':
      return 'Fallback proxy';
    case 'insufficient_data':
      return 'Insufficient data';
    default:
      return 'Unknown';
  }
}

export function formatNarrativePathway(pathway: string | null | undefined): string {
  switch (pathway) {
    case 'timeline_grammar':
      return 'Timeline grammar';
    case 'fallback_proxy':
      return 'Fallback proxy';
    case 'insufficient_data':
      return 'Insufficient data';
    default:
      return 'Unknown';
  }
}

export function formatTraceSource(source: string | null | undefined): string {
  switch (source) {
    case 'provided':
      return 'Provided traces';
    case 'synthetic_fallback':
      return 'Synthetic fallback';
    case 'mixed':
      return 'Mixed sources';
    case 'unknown':
      return 'Unknown';
    default:
      return 'Unknown';
  }
}

export function formatRewardAnticipationPathway(pathway: string | null | undefined): string {
  switch (pathway) {
    case 'timeline_dynamics':
      return 'Timeline dynamics';
    case 'fallback_proxy':
      return 'Fallback proxy';
    case 'insufficient_data':
      return 'Insufficient data';
    default:
      return 'Unknown';
  }
}

export function normalizeSeekSeconds(seconds: number): number | null {
  if (!Number.isFinite(seconds)) {
    return null;
  }
  return Math.max(0, seconds);
}

export function normalizeIndexToSignedSynchrony(value: number | null | undefined): number | null {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(-1, Math.min(1, value / 50 - 1));
}

export function isFiniteSynchrony(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value);
}
