import { describe, it, expect } from 'vitest';
import { mapReadoutToTimeline } from './readout';
import type { VideoReadout } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTracePoint(video_time_ms: number, value: number) {
  return { video_time_ms, value, scene_id: null, cut_id: null, cta_id: null };
}

function makeEmptyReadout(): VideoReadout {
  return {
    video_id: 'test-video',
    schema_version: '1.0',
    generated_at: '2026-01-01T00:00:00Z',
    traces: {
      attention_score: [],
      attention_velocity: [],
      blink_rate: [],
      blink_inhibition: [],
      reward_proxy: [],
      valence_proxy: [],
      arousal_proxy: [],
      novelty_proxy: [],
      tracking_confidence: [],
      au_channels: []
    }
  } as unknown as VideoReadout;
}

// ---------------------------------------------------------------------------
// mapReadoutToTimeline
// ---------------------------------------------------------------------------

describe('mapReadoutToTimeline', () => {
  it('returns empty array for readout with no trace data', () => {
    const readout = makeEmptyReadout();
    const result = mapReadoutToTimeline(readout);
    expect(result).toEqual([]);
  });

  it('maps attention_score trace to attentionScore field', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [
      makeTracePoint(0, 50),
      makeTracePoint(1000, 75)
    ];

    const result = mapReadoutToTimeline(readout);
    expect(result).toHaveLength(2);
    expect(result[0].attentionScore).toBe(50);
    expect(result[0].tMs).toBe(0);
    expect(result[0].tSec).toBe(0);
    expect(result[1].attentionScore).toBe(75);
    expect(result[1].tMs).toBe(1000);
    expect(result[1].tSec).toBe(1);
  });

  it('merges multiple trace series at the same timestamp', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [makeTracePoint(1000, 60)];
    readout.traces.blink_rate = [makeTracePoint(1000, 0.3)];
    readout.traces.reward_proxy = [makeTracePoint(1000, 45)];

    const result = mapReadoutToTimeline(readout);
    expect(result).toHaveLength(1);
    expect(result[0].attentionScore).toBe(60);
    expect(result[0].blinkRate).toBe(0.3);
    expect(result[0].rewardProxy).toBe(45);
  });

  it('creates separate points for different timestamps', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [makeTracePoint(0, 50)];
    readout.traces.blink_rate = [makeTracePoint(2000, 0.5)];

    const result = mapReadoutToTimeline(readout);
    expect(result).toHaveLength(2);
    expect(result[0].tMs).toBe(0);
    expect(result[0].attentionScore).toBe(50);
    expect(result[0].blinkRate).toBeNull();
    expect(result[1].tMs).toBe(2000);
    expect(result[1].attentionScore).toBeNull();
    expect(result[1].blinkRate).toBe(0.5);
  });

  it('sorts output by tMs ascending', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [
      makeTracePoint(3000, 30),
      makeTracePoint(1000, 10),
      makeTracePoint(2000, 20)
    ];

    const result = mapReadoutToTimeline(readout);
    expect(result.map((p) => p.tMs)).toEqual([1000, 2000, 3000]);
  });

  it('handles AU channels', () => {
    const readout = makeEmptyReadout();
    readout.traces.au_channels = [
      {
        au_name: 'AU12',
        points: [
          { video_time_ms: 0, value: 0.8, scene_id: null, cut_id: null, cta_id: null },
          { video_time_ms: 1000, value: 0.4, scene_id: null, cut_id: null, cta_id: null }
        ]
      },
      {
        au_name: 'AU06',
        points: [
          { video_time_ms: 0, value: 0.6, scene_id: null, cut_id: null, cta_id: null }
        ]
      }
    ];

    const result = mapReadoutToTimeline(readout);
    expect(result).toHaveLength(2);
    expect(result[0].auValues['AU12']).toBe(0.8);
    expect(result[0].auValues['AU06']).toBe(0.6);
    expect(result[1].auValues['AU12']).toBe(0.4);
    expect(result[1].auValues['AU06']).toBeUndefined();
  });

  it('populates scene_id, cut_id, cta_id from trace points', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [
      {
        video_time_ms: 1000,
        value: 50,
        scene_id: 'scene-1',
        cut_id: 'cut-1',
        cta_id: 'cta-1'
      }
    ];

    const result = mapReadoutToTimeline(readout);
    expect(result[0].sceneId).toBe('scene-1');
    expect(result[0].cutId).toBe('cut-1');
    expect(result[0].ctaId).toBe('cta-1');
  });

  it('populates median and CI fields for attention_score', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [
      {
        video_time_ms: 0,
        value: 50,
        median: 48,
        ci_low: 30,
        ci_high: 70,
        scene_id: null,
        cut_id: null,
        cta_id: null
      }
    ];

    const result = mapReadoutToTimeline(readout);
    expect(result[0].attentionScoreMedian).toBe(48);
    expect(result[0].attentionScoreCiLow).toBe(30);
    expect(result[0].attentionScoreCiHigh).toBe(70);
  });

  it('handles all trace field types', () => {
    const readout = makeEmptyReadout();
    readout.traces.attention_score = [makeTracePoint(0, 10)];
    readout.traces.attention_velocity = [makeTracePoint(0, 20)];
    readout.traces.blink_rate = [makeTracePoint(0, 30)];
    readout.traces.blink_inhibition = [makeTracePoint(0, 40)];
    readout.traces.reward_proxy = [makeTracePoint(0, 50)];
    readout.traces.valence_proxy = [makeTracePoint(0, 60)];
    readout.traces.arousal_proxy = [makeTracePoint(0, 70)];
    readout.traces.novelty_proxy = [makeTracePoint(0, 80)];
    readout.traces.tracking_confidence = [makeTracePoint(0, 90)];

    const result = mapReadoutToTimeline(readout);
    expect(result).toHaveLength(1);
    expect(result[0].attentionScore).toBe(10);
    expect(result[0].attentionVelocity).toBe(20);
    expect(result[0].blinkRate).toBe(30);
    expect(result[0].blinkInhibition).toBe(40);
    expect(result[0].rewardProxy).toBe(50);
    expect(result[0].valenceProxy).toBe(60);
    expect(result[0].arousalProxy).toBe(70);
    expect(result[0].noveltyProxy).toBe(80);
    expect(result[0].trackingConfidence).toBe(90);
  });
});
