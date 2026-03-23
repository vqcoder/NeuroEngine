/**
 * Client-side engagement prediction for reordered video scenes.
 *
 * Researchers define scene split points interactively, then drag scenes
 * to simulate reordering.  All computation runs in the browser — no API needed.
 */

import type { PredictorTimelinePoint } from './predictorTimeline';

// ── Types ──────────────────────────────────────────────────────────────────

export type SceneSegment = {
  id: string;
  label: string;
  startSec: number;
  endSec: number;
  avgAttention: number;
  avgReward: number;
  /** Original trace points belonging to this scene. */
  points: PredictorTimelinePoint[];
};

export type SimulationResult = {
  originalScore: number;
  simulatedScore: number;
  deltaPercent: number;
  originalTrace: number[];
  simulatedTrace: number[];
};

// ── Functions ──────────────────────────────────────────────────────────────

export function buildScenesFromTrace(
  trace: PredictorTimelinePoint[],
  splitPoints: number[],
): SceneSegment[] {
  if (trace.length === 0) return [];

  const sorted = [...trace].sort((a, b) => a.tSec - b.tSec);
  const cuts = [...new Set(splitPoints)].sort((a, b) => a - b);

  // Build boundary array: [start, cut1, cut2, ..., end]
  const firstSec = sorted[0].tSec;
  const lastSec = sorted[sorted.length - 1].tSec;
  const boundaries = [
    firstSec,
    ...cuts.filter((c) => c > firstSec && c < lastSec),
    lastSec + 0.001, // tiny epsilon so the last point is included
  ];

  const scenes: SceneSegment[] = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const lo = boundaries[i];
    const hi = boundaries[i + 1];
    const points = sorted.filter((p) => p.tSec >= lo && p.tSec < hi);
    if (points.length === 0) continue;

    const avgAttention =
      points.reduce((sum, p) => sum + p.attentionScore, 0) / points.length;
    const avgReward =
      points.reduce((sum, p) => sum + p.rewardProxy, 0) / points.length;

    scenes.push({
      id: `scene-${i + 1}`,
      label: `Scene ${i + 1}`,
      startSec: points[0].tSec,
      endSec: points[points.length - 1].tSec,
      avgAttention: Math.round(avgAttention * 100) / 100,
      avgReward: Math.round(avgReward * 100) / 100,
      points,
    });
  }

  return scenes;
}

export function simulateReorder(
  scenes: SceneSegment[],
  newOrder: string[],
): SimulationResult {
  const sceneMap = new Map(scenes.map((s) => [s.id, s]));
  const reordered = newOrder
    .map((id) => sceneMap.get(id))
    .filter((s): s is SceneSegment => s !== undefined);

  const originalTrace = scenes.flatMap((s) => s.points.map((p) => p.attentionScore));
  const simulatedTrace = reordered.flatMap((s) => s.points.map((p) => p.attentionScore));

  const mean = (arr: number[]) =>
    arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;

  const originalScore = Math.round(mean(originalTrace) * 100) / 100;
  const simulatedScore = Math.round(mean(simulatedTrace) * 100) / 100;
  const deltaPercent =
    originalScore !== 0
      ? Math.round(((simulatedScore - originalScore) / originalScore) * 1000) / 10
      : 0;

  return { originalScore, simulatedScore, deltaPercent, originalTrace, simulatedTrace };
}

export function formatDelta(deltaPercent: number): string {
  if (deltaPercent === 0) return '0.0%';
  const sign = deltaPercent > 0 ? '+' : '';
  return `${sign}${deltaPercent.toFixed(1)}%`;
}

export function getEngagementColour(avgAttention: number): 'green' | 'amber' | 'red' {
  if (avgAttention > 70) return 'green';
  if (avgAttention >= 40) return 'amber';
  return 'red';
}
