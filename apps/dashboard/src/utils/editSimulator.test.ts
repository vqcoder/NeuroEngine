import { describe, it, expect } from 'vitest';
import type { PredictorTimelinePoint } from './predictorTimeline';
import {
  buildScenesFromTrace,
  simulateReorder,
  formatDelta,
  getEngagementColour,
} from './editSimulator';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePoint(tSec: number, attention = 50, reward = 40): PredictorTimelinePoint {
  return {
    tSec,
    attentionScore: attention,
    rewardProxy: reward,
    attentionVelocity: 0,
    blinkInhibition: 0,
    blinkRate: 0,
    dial: 50,
    valenceProxy: 0,
    arousalProxy: 0,
    noveltyProxy: 0,
    trackingConfidence: 1,
  };
}

// ---------------------------------------------------------------------------
// buildScenesFromTrace
// ---------------------------------------------------------------------------

describe('buildScenesFromTrace', () => {
  it('returns 1 scene covering full trace when no split points', () => {
    const trace = [makePoint(0), makePoint(30), makePoint(60)];
    const scenes = buildScenesFromTrace(trace, []);
    expect(scenes).toHaveLength(1);
    expect(scenes[0].label).toBe('Scene 1');
    expect(scenes[0].points).toHaveLength(3);
  });

  it('returns 2 scenes when split at 30s on a 60s trace', () => {
    const trace = [
      makePoint(0, 60),
      makePoint(15, 60),
      makePoint(30, 80),
      makePoint(45, 80),
      makePoint(60, 80),
    ];
    const scenes = buildScenesFromTrace(trace, [30]);
    expect(scenes).toHaveLength(2);
    expect(scenes[0].label).toBe('Scene 1');
    expect(scenes[1].label).toBe('Scene 2');
    expect(scenes[0].points.length).toBe(2); // 0s, 15s
    expect(scenes[1].points.length).toBe(3); // 30s, 45s, 60s
  });
});

// ---------------------------------------------------------------------------
// simulateReorder
// ---------------------------------------------------------------------------

describe('simulateReorder', () => {
  it('produces correct simulatedTrace when 2 scenes are reversed', () => {
    const trace = [
      makePoint(0, 20),
      makePoint(10, 20),
      makePoint(20, 80),
      makePoint(30, 80),
    ];
    const scenes = buildScenesFromTrace(trace, [20]);
    expect(scenes).toHaveLength(2);

    const reversed = [scenes[1].id, scenes[0].id];
    const result = simulateReorder(scenes, reversed);

    // Simulated trace should be [80, 80, 20, 20]
    expect(result.simulatedTrace).toEqual([80, 80, 20, 20]);
    // Original trace should be [20, 20, 80, 80]
    expect(result.originalTrace).toEqual([20, 20, 80, 80]);
    // Mean is the same (50), so delta should be 0
    expect(result.deltaPercent).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// formatDelta
// ---------------------------------------------------------------------------

describe('formatDelta', () => {
  it('formats positive delta', () => {
    expect(formatDelta(5.234)).toBe('+5.2%');
  });

  it('formats negative delta', () => {
    expect(formatDelta(-3.1)).toBe('-3.1%');
  });

  it('formats zero', () => {
    expect(formatDelta(0)).toBe('0.0%');
  });
});

// ---------------------------------------------------------------------------
// getEngagementColour
// ---------------------------------------------------------------------------

describe('getEngagementColour', () => {
  it('returns green for high attention', () => {
    expect(getEngagementColour(80)).toBe('green');
  });

  it('returns amber for medium attention', () => {
    expect(getEngagementColour(55)).toBe('amber');
  });

  it('returns red for low attention', () => {
    expect(getEngagementColour(30)).toBe('red');
  });
});
