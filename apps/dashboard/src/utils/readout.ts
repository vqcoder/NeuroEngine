import type {
  ReadoutTimelinePoint,
  VideoReadout
} from '../types';

type MutableTimelinePoint = {
  tMs: number;
  tSec: number;
  sceneId: string | null;
  cutId: string | null;
  ctaId: string | null;
  attentionScore: number | null;
  attentionScoreMedian?: number | null;
  attentionScoreCiLow?: number | null;
  attentionScoreCiHigh?: number | null;
  attentionVelocity: number | null;
  blinkRate: number | null;
  blinkInhibition: number | null;
  rewardProxy: number | null;
  rewardProxyMedian?: number | null;
  rewardProxyCiLow?: number | null;
  rewardProxyCiHigh?: number | null;
  valenceProxy: number | null;
  arousalProxy: number | null;
  noveltyProxy: number | null;
  trackingConfidence: number | null;
  auValues: Record<string, number | null>;
};

function ensureTimelinePoint(
  map: Map<number, MutableTimelinePoint>,
  tMs: number
): MutableTimelinePoint {
  const existing = map.get(tMs);
  if (existing) {
    return existing;
  }

  const created: MutableTimelinePoint = {
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
  map.set(tMs, created);
  return created;
}

function setTraceField(
  map: Map<number, MutableTimelinePoint>,
  series: VideoReadout['traces']['attention_score'],
  field:
    | 'attentionScore'
    | 'attentionVelocity'
    | 'blinkRate'
    | 'blinkInhibition'
    | 'rewardProxy'
    | 'valenceProxy'
    | 'arousalProxy'
    | 'noveltyProxy'
    | 'trackingConfidence',
  options?: {
    medianField?: 'attentionScoreMedian' | 'rewardProxyMedian';
    ciLowField?: 'attentionScoreCiLow' | 'rewardProxyCiLow';
    ciHighField?: 'attentionScoreCiHigh' | 'rewardProxyCiHigh';
  }
): void {
  series.forEach((point) => {
    const target = ensureTimelinePoint(map, point.video_time_ms);
    target[field] = point.value;
    if (options?.medianField) {
      target[options.medianField] = point.median ?? null;
    }
    if (options?.ciLowField) {
      target[options.ciLowField] = point.ci_low ?? null;
    }
    if (options?.ciHighField) {
      target[options.ciHighField] = point.ci_high ?? null;
    }
    if (!target.sceneId && point.scene_id) {
      target.sceneId = point.scene_id;
    }
    if (!target.cutId && point.cut_id) {
      target.cutId = point.cut_id;
    }
    if (!target.ctaId && point.cta_id) {
      target.ctaId = point.cta_id;
    }
  });
}

export function mapReadoutToTimeline(readout: VideoReadout): ReadoutTimelinePoint[] {
  const byMs = new Map<number, MutableTimelinePoint>();

  setTraceField(byMs, readout.traces.attention_score, 'attentionScore', {
    medianField: 'attentionScoreMedian',
    ciLowField: 'attentionScoreCiLow',
    ciHighField: 'attentionScoreCiHigh'
  });
  setTraceField(byMs, readout.traces.attention_velocity, 'attentionVelocity');
  setTraceField(byMs, readout.traces.blink_rate, 'blinkRate');
  setTraceField(byMs, readout.traces.blink_inhibition, 'blinkInhibition');
  setTraceField(byMs, readout.traces.reward_proxy, 'rewardProxy', {
    medianField: 'rewardProxyMedian',
    ciLowField: 'rewardProxyCiLow',
    ciHighField: 'rewardProxyCiHigh'
  });
  setTraceField(byMs, readout.traces.valence_proxy, 'valenceProxy');
  setTraceField(byMs, readout.traces.arousal_proxy, 'arousalProxy');
  setTraceField(byMs, readout.traces.novelty_proxy, 'noveltyProxy');
  setTraceField(byMs, readout.traces.tracking_confidence, 'trackingConfidence');

  readout.traces.au_channels.forEach((channel) => {
    channel.points.forEach((point) => {
      const target = ensureTimelinePoint(byMs, point.video_time_ms);
      target.auValues[channel.au_name] = point.value;
      if (!target.sceneId && point.scene_id) {
        target.sceneId = point.scene_id;
      }
      if (!target.cutId && point.cut_id) {
        target.cutId = point.cut_id;
      }
      if (!target.ctaId && point.cta_id) {
        target.ctaId = point.cta_id;
      }
    });
  });

  return [...byMs.values()].sort((a, b) => a.tMs - b.tMs);
}
