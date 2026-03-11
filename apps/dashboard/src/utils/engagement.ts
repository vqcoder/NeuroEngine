import type {
  DeadZone,
  EngagementPeak,
  SceneMetric,
  TimelinePoint,
  VideoSummary
} from '../types';

function clamp(value: number, min = 0, max = 100): number {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
}

function percentile(values: number[], percentileValue: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.floor((sorted.length - 1) * percentileValue);
  return sorted[index];
}

function lookupSceneLabel(sceneMetrics: SceneMetric[], tMs: number): string {
  const scene = sceneMetrics.find((item) => tMs >= item.start_ms && tMs < item.end_ms);
  return scene?.label ?? 'Unlabeled';
}

function scaleAttention(rawValues: number[]): number[] {
  if (rawValues.length === 0) {
    return [];
  }

  const min = Math.min(...rawValues);
  const max = Math.max(...rawValues);
  if (Math.abs(max - min) < 1e-9) {
    return rawValues.map(() => 50);
  }

  return rawValues.map((value) => clamp(((value - min) / (max - min)) * 100));
}

export function mapSummaryToTimeline(summary: VideoSummary): TimelinePoint[] {
  const buckets =
    summary.passive_traces && summary.passive_traces.length > 0
      ? summary.passive_traces
      : summary.trace_buckets;

  const rawAttention = buckets.map((bucket) => {
    const au12 = bucket.mean_au_norm.AU12 ?? 0;
    const au6 = bucket.mean_au_norm.AU06 ?? 0;
    const au4 = bucket.mean_au_norm.AU04 ?? 0;
    const blinkRate = bucket.blink_rate ?? 0;
    const rewardProxy = bucket.mean_reward_proxy ?? null;
    const rewardSignal = rewardProxy !== null ? rewardProxy / 100 : 0;

    return au12 * 0.5 + au6 * 0.25 - au4 * 0.2 - blinkRate * 0.35 + rewardSignal * 0.4;
  });

  const scaledAttention = scaleAttention(rawAttention);

  return buckets.map((bucket, index) => ({
    tMs: bucket.bucket_start_ms,
    tSec: bucket.bucket_start_ms / 1000,
    attention: Number(scaledAttention[index].toFixed(4)),
    dial: bucket.mean_dial !== null ? Number(bucket.mean_dial.toFixed(4)) : null,
    blinkRate: Number((bucket.blink_rate ?? 0).toFixed(4)),
    blinkInhibition: Number((bucket.mean_blink_inhibition_score ?? 0).toFixed(4)),
    rewardProxy:
      bucket.mean_reward_proxy !== null && bucket.mean_reward_proxy !== undefined
        ? Number(bucket.mean_reward_proxy.toFixed(4))
        : null,
    gazeProxy:
      bucket.mean_gaze_on_screen_proxy !== null && bucket.mean_gaze_on_screen_proxy !== undefined
        ? Number(bucket.mean_gaze_on_screen_proxy.toFixed(4))
        : null,
    qualityScore:
      bucket.mean_quality_score !== null && bucket.mean_quality_score !== undefined
        ? Number(bucket.mean_quality_score.toFixed(4))
        : null,
    qualityConfidence:
      bucket.mean_quality_confidence !== null && bucket.mean_quality_confidence !== undefined
        ? Number(bucket.mean_quality_confidence.toFixed(4))
        : null,
    faceOkRate: Number((bucket.face_ok_rate ?? 0).toFixed(4)),
    sceneId: bucket.scene_id ?? null,
    cutId: bucket.cut_id ?? null,
    ctaId: bucket.cta_id ?? null,
    au12: Number((bucket.mean_au_norm.AU12 ?? 0).toFixed(4)),
    au6: Number((bucket.mean_au_norm.AU06 ?? 0).toFixed(4)),
    au4: Number((bucket.mean_au_norm.AU04 ?? 0).toFixed(4))
  }));
}

export function computeGoldenScenes(
  points: TimelinePoint[],
  sceneMetrics: SceneMetric[],
  limit = 5
): EngagementPeak[] {
  if (points.length === 0) {
    return [];
  }

  const candidates: EngagementPeak[] = points.map((point, index) => {
    const previous = points[index - 1]?.attention ?? point.attention;
    const next = points[index + 1]?.attention ?? point.attention;
    const localityBoost = point.attention >= previous && point.attention >= next ? 4 : 0;
    const rewardSignal = point.rewardProxy ?? point.attention;

    return {
      tSec: point.tSec,
      score: Number((point.attention * 0.7 + rewardSignal * 0.3 + localityBoost).toFixed(4)),
      rewardProxy: point.rewardProxy,
      sceneLabel: lookupSceneLabel(sceneMetrics, point.tMs)
    };
  });

  return candidates
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => ({ ...item, score: Number(item.score.toFixed(2)) }));
}

export function computeDeadZones(
  points: TimelinePoint[],
  sceneMetrics: SceneMetric[],
  limit = 5
): DeadZone[] {
  if (points.length === 0) {
    return [];
  }

  const threshold = percentile(
    points.map((point) => point.attention),
    0.3
  );
  const blinkFrictionThreshold = percentile(
    points.map((point) => point.blinkRate),
    0.7
  );
  const au4FrictionThreshold = percentile(
    points.map((point) => point.au4),
    0.7
  );

  const zones: DeadZone[] = [];
  let startIndex = -1;

  for (let i = 0; i < points.length; i += 1) {
    const isAttentionDrop = points[i].attention <= threshold;
    const isFriction = points[i].blinkRate >= blinkFrictionThreshold && points[i].au4 >= au4FrictionThreshold;
    const below = isAttentionDrop || isFriction;

    if (below && startIndex === -1) {
      startIndex = i;
    }

    const shouldClose = startIndex !== -1 && (!below || i === points.length - 1);
    if (shouldClose) {
      const endIndex = below && i === points.length - 1 ? i : i - 1;
      const slice = points.slice(startIndex, endIndex + 1);

      if (slice.length >= 2) {
        const startSec = slice[0].tSec;
        const endSec = slice[slice.length - 1].tSec;
        const meanAttention = slice.reduce((sum, point) => sum + point.attention, 0) / slice.length;
        const frictionScore =
          slice.reduce((sum, point) => sum + point.blinkRate * 40 + point.au4 * 30, 0) /
          slice.length;
        zones.push({
          startSec,
          endSec,
          durationSec: endSec - startSec + 1,
          meanAttention: Number(meanAttention.toFixed(2)),
          frictionScore: Number(frictionScore.toFixed(2)),
          sceneLabel: lookupSceneLabel(sceneMetrics, slice[0].tMs)
        });
      }

      startIndex = -1;
    }
  }

  return zones
    .sort((a, b) => {
      if (b.durationSec !== a.durationSec) {
        return b.durationSec - a.durationSec;
      }
      return a.meanAttention - b.meanAttention;
    })
    .slice(0, limit);
}
