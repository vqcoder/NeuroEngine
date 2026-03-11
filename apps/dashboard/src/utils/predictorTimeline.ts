import type { PredictTracePoint } from '../types';
import {
  TRACK_ORDER,
  type TimelineKeyMoment,
  type TimelineKeyMomentType,
  type TimelineTrack,
  type TimelineTrackKey,
  type TimelineTrackWindow
} from './timelineReport';
import {
  isHttpUrl,
  normalizeLegacyAssetProxyUrl,
  unwrapHlsProxySourceUrl,
} from './videoDashboard';

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

export type PredictorTimelinePoint = {
  tSec: number;
  attentionScore: number;
  rewardProxy: number;
  attentionVelocity: number;
  blinkInhibition: number;
  blinkRate: number;
  dial: number;
  valenceProxy: number;
  arousalProxy: number;
  noveltyProxy: number;
  trackingConfidence: number;
};

export type PredictorLayerVisibility = {
  attentionScore: boolean;
  rewardProxy: boolean;
  dial: boolean;
  valenceProxy: boolean;
  arousalProxy: boolean;
  noveltyProxy: boolean;
  attentionVelocity: boolean;
  blinkInhibition: boolean;
  blinkRate: boolean;
  trackingConfidence: boolean;
};

export type PredictorTimelineEvent = {
  id: string;
  tSec: number;
  title: string;
  secondary: string;
};

export type PredictorChartClickState = {
  activeLabel?: number | string;
};

export const DEFAULT_LAYER_VISIBILITY: PredictorLayerVisibility = {
  attentionScore: true,
  rewardProxy: true,
  dial: true,
  valenceProxy: true,
  arousalProxy: true,
  noveltyProxy: true,
  attentionVelocity: true,
  blinkInhibition: true,
  blinkRate: true,
  trackingConfidence: false
};

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function toSeekableSecond(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Number(value.toFixed(3)));
}

export function formatSeconds(value: number): string {
  return `${toSeekableSecond(value).toFixed(1)}s`;
}

const DIRECT_VIDEO_EXTENSION_PATTERN = /\.(mp4|mov|m4v|webm|m3u8|mpd)(?:[?#].*)?$/i;

export function normalizePredictorInputUrl(value: string): string {
  const normalizedLegacy = normalizeLegacyAssetProxyUrl(value.trim());
  if (isHttpUrl(normalizedLegacy)) {
    return normalizedLegacy;
  }
  if (normalizedLegacy.startsWith('/') && typeof window !== 'undefined') {
    return `${window.location.origin}${normalizedLegacy}`;
  }
  return normalizedLegacy;
}

export function isLikelyDirectVideoUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.startsWith('/')) {
    return DIRECT_VIDEO_EXTENSION_PATTERN.test(trimmed);
  }
  try {
    const parsed = new URL(trimmed);
    const path = parsed.pathname.toLowerCase();
    if (['.mp4', '.mov', '.m4v', '.webm', '.m3u8', '.mpd'].some((suffix) => path.endsWith(suffix))) {
      return true;
    }

    const host = parsed.hostname.toLowerCase();
    if (host.includes('googlevideo.com') && path.includes('/videoplayback')) {
      return true;
    }
    if (parsed.searchParams.get('mime')?.startsWith('video/')) {
      return true;
    }

    return false;
  } catch (_error) {
    return false;
  }
}

export function buildPlaybackCandidates(...urls: string[]): string[] {
  const candidates: string[] = [];
  for (const rawUrl of urls) {
    const trimmed = rawUrl.trim();
    if (!trimmed) {
      continue;
    }
    const unwrapped = unwrapHlsProxySourceUrl(trimmed);
    const expanded = [trimmed, ...(unwrapped ? [unwrapped] : [])];
    for (const rawCandidate of expanded) {
      const normalizedLegacy = normalizeLegacyAssetProxyUrl(rawCandidate);
      for (const candidate of [rawCandidate, normalizedLegacy]) {
        if (candidate && isLikelyDirectVideoUrl(candidate)) {
          candidates.push(candidate);
        }
      }
    }
  }
  return [...new Set(candidates)];
}

// ---------------------------------------------------------------------------
// Timeline derivation
// ---------------------------------------------------------------------------

export function deriveTimeline(points: PredictTracePoint[]): PredictorTimelinePoint[] {
  const sorted = [...points].sort((a, b) => a.t_sec - b.t_sec);
  let previousAttention: number | null = null;
  let previousSec: number | null = null;

  return sorted.map((point) => {
    const blinkInhibitionNorm = clamp(point.blink_inhibition / 100, 0, 1);
    const attentionScore = point.attention ?? clamp(30 + blinkInhibitionNorm * 55, 0, 100);
    const rewardProxy =
      point.reward_proxy ??
      clamp(attentionScore * 0.55 + (1 - blinkInhibitionNorm) * 30 + point.dial * 0.15, 0, 100);
    const dt = previousSec === null ? 1 : Math.max(0.001, point.t_sec - previousSec);
    const derivedAttentionVelocity =
      previousAttention === null ? 0 : Number(((attentionScore - previousAttention) / dt).toFixed(4));
    const attentionVelocity =
      point.attention_velocity == null
        ? derivedAttentionVelocity
        : Number(point.attention_velocity.toFixed(4));

    const blinkRate =
      point.blink_rate == null
        ? clamp(0.45 - 0.35 * blinkInhibitionNorm, 0.02, 0.85)
        : clamp(point.blink_rate, 0.02, 0.85);
    const valenceProxy =
      point.valence_proxy == null
        ? clamp(attentionScore * 0.65 + point.dial * 0.35, 0, 100)
        : clamp(point.valence_proxy, 0, 100);
    const arousalProxy =
      point.arousal_proxy == null
        ? clamp(25 + Math.abs(attentionVelocity) * 5 + Math.max(0, -point.blink_inhibition) * 20, 0, 100)
        : clamp(point.arousal_proxy, 0, 100);
    const noveltyProxy =
      point.novelty_proxy == null
        ? clamp(15 + Math.abs(attentionVelocity) * 8, 0, 100)
        : clamp(point.novelty_proxy, 0, 100);

    const trackingConfidence = clamp(point.tracking_confidence ?? 1.0, 0, 1);

    previousAttention = attentionScore;
    previousSec = point.t_sec;

    return {
      tSec: Number(point.t_sec.toFixed(3)),
      attentionScore: Number(attentionScore.toFixed(4)),
      rewardProxy: Number(rewardProxy.toFixed(4)),
      attentionVelocity,
      blinkInhibition: Number(point.blink_inhibition.toFixed(4)),
      blinkRate: Number(blinkRate.toFixed(4)),
      dial: Number(point.dial.toFixed(4)),
      valenceProxy: Number(valenceProxy.toFixed(4)),
      arousalProxy: Number(arousalProxy.toFixed(4)),
      noveltyProxy: Number(noveltyProxy.toFixed(4)),
      trackingConfidence
    };
  });
}

// ---------------------------------------------------------------------------
// Synthetic track + key-moment derivation from predictor trace data
// ---------------------------------------------------------------------------

function mergeAdjacentWindows(
  windows: Array<{ startMs: number; endMs: number; reason: string; score: number }>,
  maxGapMs: number
): Array<{ startMs: number; endMs: number; reason: string; score: number }> {
  if (windows.length === 0) {
    return [];
  }
  const sorted = [...windows].sort((a, b) => a.startMs - b.startMs);
  const merged: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [{ ...sorted[0] }];
  for (let i = 1; i < sorted.length; i++) {
    const last = merged[merged.length - 1];
    const curr = sorted[i];
    if (curr.startMs - last.endMs <= maxGapMs) {
      last.endMs = Math.max(last.endMs, curr.endMs);
      last.score = Math.max(last.score, curr.score);
    } else {
      merged.push({ ...curr });
    }
  }
  return merged;
}

function toTrackWindow(
  w: { startMs: number; endMs: number; reason: string; score: number }
): TimelineTrackWindow {
  return {
    start_ms: w.startMs,
    end_ms: w.endMs,
    reason: w.reason,
    source: 'predictor_proxy',
    score: Number(w.score.toFixed(3)),
    confidence: null
  };
}

export function derivePredictorTracks(
  timeline: PredictorTimelinePoint[],
  durationSec: number
): TimelineTrack[] {
  const durationMs = Math.round(durationSec * 1000);
  const stepMs = timeline.length > 1
    ? Math.round(((timeline[timeline.length - 1].tSec - timeline[0].tSec) / (timeline.length - 1)) * 1000)
    : 1000;

  // ----- attention_arrest: high reward / attention windows -----
  const arrestRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.rewardProxy >= 65) {
      const ms = Math.round(pt.tSec * 1000);
      arrestRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'High reward proxy — sustained viewer hold', score: pt.rewardProxy });
    }
  });
  const arrestWindows = mergeAdjacentWindows(arrestRaw, stepMs * 2).map(toTrackWindow);

  // ----- attentional_synchrony: stable + high attention -----
  const syncRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.attentionScore >= 55 && Math.abs(pt.attentionVelocity) < 5) {
      const ms = Math.round(pt.tSec * 1000);
      syncRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'Stable high attention — convergence proxy', score: pt.attentionScore });
    }
  });
  const syncWindows = mergeAdjacentWindows(syncRaw, stepMs * 2)
    .filter((w) => w.endMs - w.startMs >= 1500)
    .map(toTrackWindow);

  // ----- narrative_control: sustained upward attention trend -----
  const narRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.attentionVelocity > 3) {
      const ms = Math.round(pt.tSec * 1000);
      narRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'Ascending attention trend — narrative pull proxy', score: clamp(pt.attentionVelocity * 2, 0, 100) });
    }
  });
  const narWindows = mergeAdjacentWindows(narRaw, stepMs * 3)
    .filter((w) => w.endMs - w.startMs >= 2000)
    .map(toTrackWindow);

  // ----- blink_transport: blink suppression windows -----
  const blinkRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.blinkInhibition < -15) {
      const ms = Math.round(pt.tSec * 1000);
      blinkRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'Blink suppression — attentional gating proxy', score: clamp(Math.abs(pt.blinkInhibition), 0, 100) });
    }
  });
  const blinkWindows = mergeAdjacentWindows(blinkRaw, stepMs * 2).map(toTrackWindow);

  // ----- reward_anticipation: reward ramp windows -----
  const rampRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.attentionVelocity > 2 && pt.rewardProxy < 75) {
      const ms = Math.round(pt.tSec * 1000);
      rampRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'Reward ramp — anticipatory build proxy', score: pt.rewardProxy });
    }
  });
  // payoff windows: top reward moments following a ramp
  const payoffRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.rewardProxy >= 72 && pt.attentionVelocity <= 0) {
      const ms = Math.round(pt.tSec * 1000);
      payoffRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'Reward payoff — peak release proxy', score: pt.rewardProxy });
    }
  });
  const rewardWindows = [
    ...mergeAdjacentWindows(rampRaw, stepMs * 2),
    ...mergeAdjacentWindows(payoffRaw, stepMs * 2)
  ]
    .sort((a, b) => a.startMs - b.startMs)
    .map(toTrackWindow);

  // ----- boundary_encoding: sharp attention transitions -----
  const boundaryRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (Math.abs(pt.attentionVelocity) > 20) {
      const ms = Math.round(pt.tSec * 1000);
      const halfMs = Math.max(250, stepMs);
      boundaryRaw.push({ startMs: Math.max(0, ms - halfMs), endMs: Math.min(durationMs, ms + halfMs), reason: 'Sharp attention transition — edit boundary encoding proxy', score: clamp(Math.abs(pt.attentionVelocity), 0, 100) });
    }
  });
  const boundaryWindows = mergeAdjacentWindows(boundaryRaw, stepMs).map(toTrackWindow);

  // ----- cta_reception: unavailable without CTA markers -----
  const ctaWindows: TimelineTrackWindow[] = [];

  // ----- au_friction: high arousal + low reward proxy -----
  const frictionRaw: Array<{ startMs: number; endMs: number; reason: string; score: number }> = [];
  timeline.forEach((pt) => {
    if (pt.arousalProxy > 68 && pt.rewardProxy < 42) {
      const ms = Math.round(pt.tSec * 1000);
      frictionRaw.push({ startMs: ms, endMs: ms + stepMs, reason: 'High arousal / low reward — AU friction proxy', score: pt.arousalProxy });
    }
  });
  const frictionWindows = mergeAdjacentWindows(frictionRaw, stepMs * 2).map(toTrackWindow);

  const TRACK_META_PREDICTOR: Record<TimelineTrackKey, { label: string; description: string; color: string }> = {
    attention_arrest: { label: 'Attention / Arrest', description: 'High reward-proxy windows — predicted sustained viewer hold.', color: '#2f7dff' },
    attentional_synchrony: { label: 'Attentional Synchrony', description: 'Stable high-attention windows — predicted viewer convergence proxy.', color: '#19c6ff' },
    narrative_control: { label: 'Narrative Control', description: 'Ascending attention trend windows — predicted narrative pull.', color: '#7cb8ff' },
    blink_transport: { label: 'Blink Transport', description: 'Blink suppression windows — predicted attentional gating proxy.', color: '#58d4c1' },
    reward_anticipation: { label: 'Reward Anticipation', description: 'Reward ramp and payoff windows — predicted setup-to-payoff dynamics.', color: '#ff8f3d' },
    boundary_encoding: { label: 'Boundary Encoding', description: 'Sharp attention transitions — predicted event boundary encoding.', color: '#a485ff' },
    cta_reception: { label: 'CTA Reception', description: 'Not available in predictor mode — requires explicit CTA markers.', color: '#ffb347' },
    au_friction: { label: 'AU Friction', description: 'High arousal / low reward windows — facial friction proxy from trace dynamics.', color: '#f06292' }
  };

  const windowsByKey: Record<TimelineTrackKey, TimelineTrackWindow[]> = {
    attention_arrest: arrestWindows,
    attentional_synchrony: syncWindows,
    narrative_control: narWindows,
    blink_transport: blinkWindows,
    reward_anticipation: rewardWindows,
    boundary_encoding: boundaryWindows,
    cta_reception: ctaWindows,
    au_friction: frictionWindows
  };

  return TRACK_ORDER.map((key) => {
    const meta = TRACK_META_PREDICTOR[key];
    return {
      key,
      machineName: key === 'attention_arrest' ? 'arrest_score'
        : key === 'attentional_synchrony' ? 'attentional_synchrony_index'
        : key === 'narrative_control' ? 'narrative_control_score'
        : key === 'blink_transport' ? 'blink_transport_score'
        : key === 'reward_anticipation' ? 'reward_anticipation_index'
        : key === 'boundary_encoding' ? 'boundary_encoding_score'
        : key === 'cta_reception' ? 'cta_reception_score'
        : 'au_friction_score',
      label: meta.label,
      description: meta.description,
      color: meta.color,
      windows: windowsByKey[key]
    };
  });
}

export function derivePredictorKeyMoments(
  timeline: PredictorTimelinePoint[],
  durationSec: number
): TimelineKeyMoment[] {
  const durationMs = Math.round(durationSec * 1000);
  const moments: TimelineKeyMoment[] = [];
  const dedupe = new Set<string>();

  const push = (
    type: TimelineKeyMomentType,
    startMs: number,
    endMs: number,
    reason: string,
    label: string,
    color: string
  ) => {
    const key = `${type}:${Math.round(startMs)}:${Math.round(endMs)}`;
    if (dedupe.has(key)) return;
    dedupe.add(key);
    const safeStart = clamp(Math.round(startMs), 0, durationMs);
    const safeEnd = clamp(Math.round(endMs), 0, durationMs);
    if (safeEnd <= safeStart) return;
    moments.push({ type, label, start_ms: safeStart, end_ms: safeEnd, reason, color });
  };

  // Hook window: first 3s
  push('hook_window', 0, Math.min(durationMs, 3000), 'Opening hook window (first 1-3 seconds)', 'Hook window', '#22c55e');

  // Reward ramps
  let rampStart: number | null = null;
  timeline.forEach((pt, i) => {
    const ms = Math.round(pt.tSec * 1000);
    if (pt.attentionVelocity > 2 && pt.rewardProxy < 75) {
      if (rampStart === null) rampStart = ms;
    } else {
      if (rampStart !== null && ms - rampStart >= 1500) {
        push('reward_ramp', rampStart, ms, 'Reward anticipation ramp', 'Reward ramp', '#fb923c');
      }
      rampStart = null;
    }
    if (i === timeline.length - 1 && rampStart !== null && ms - rampStart >= 1500) {
      push('reward_ramp', rampStart, ms, 'Reward anticipation ramp', 'Reward ramp', '#fb923c');
    }
  });

  // Dead zones: low attention for >= 2s
  let deadStart: number | null = null;
  timeline.forEach((pt, i) => {
    const ms = Math.round(pt.tSec * 1000);
    if (pt.attentionScore < 35 && pt.rewardProxy < 35) {
      if (deadStart === null) deadStart = ms;
    } else {
      if (deadStart !== null && ms - deadStart >= 2000) {
        push('dead_zone', deadStart, ms, 'Low attention / low reward — drop-off risk', 'Dead zone / drop-off risk', '#ef4444');
      }
      deadStart = null;
    }
    if (i === timeline.length - 1 && deadStart !== null && ms - deadStart >= 2000) {
      push('dead_zone', deadStart, ms, 'Low attention / low reward — drop-off risk', 'Dead zone / drop-off risk', '#ef4444');
    }
  });

  moments.sort((a, b) => a.start_ms - b.start_ms || a.end_ms - b.end_ms);
  return moments;
}

// ---------------------------------------------------------------------------
// Timeline event derivation
// ---------------------------------------------------------------------------

export function deriveTimelineEvents(timeline: PredictorTimelinePoint[]): PredictorTimelineEvent[] {
  if (timeline.length === 0) {
    return [];
  }

  const topRewardEvents = [...timeline]
    .sort((a, b) => b.rewardProxy - a.rewardProxy)
    .slice(0, 3)
    .map((point, index) => ({
      id: `reward-${index}-${point.tSec}`,
      tSec: point.tSec,
      title: index === 0 ? 'Peak reward moment' : `Reward peak #${index + 1}`,
      secondary: `reward_proxy ${point.rewardProxy.toFixed(1)}`
    }));

  const steepDrop = [...timeline]
    .sort((a, b) => a.attentionVelocity - b.attentionVelocity)
    .find((point) => point.attentionVelocity < 0);
  const rebound = [...timeline]
    .sort((a, b) => b.attentionVelocity - a.attentionVelocity)
    .find((point) => point.attentionVelocity > 0);

  const velocityEvents: PredictorTimelineEvent[] = [];
  if (steepDrop) {
    velocityEvents.push({
      id: `drop-${steepDrop.tSec}`,
      tSec: steepDrop.tSec,
      title: 'Steepest attention drop',
      secondary: `velocity ${steepDrop.attentionVelocity.toFixed(2)}`
    });
  }
  if (rebound) {
    velocityEvents.push({
      id: `rebound-${rebound.tSec}`,
      tSec: rebound.tSec,
      title: 'Strongest attention rebound',
      secondary: `velocity +${rebound.attentionVelocity.toFixed(2)}`
    });
  }

  const bySecond = new Map<number, PredictorTimelineEvent>();
  [...topRewardEvents, ...velocityEvents].forEach((item) => {
    const key = toSeekableSecond(item.tSec);
    if (!bySecond.has(key)) {
      bySecond.set(key, { ...item, tSec: key });
    }
  });

  return [...bySecond.values()].sort((a, b) => a.tSec - b.tSec);
}
