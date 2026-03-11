import type {
  NeuroScoreMachineName,
  ReadoutDiagnosticCard,
  ReadoutSegment,
  VideoReadout
} from '../types';

export type TimelineTrackKey =
  | 'attention_arrest'
  | 'attentional_synchrony'
  | 'narrative_control'
  | 'blink_transport'
  | 'reward_anticipation'
  | 'boundary_encoding'
  | 'cta_reception'
  | 'au_friction';

export type TimelineTrackVisibility = Record<TimelineTrackKey, boolean>;

export type TimelineTrackWindow = {
  start_ms: number;
  end_ms: number;
  reason: string;
  source: string;
  score?: number | null;
  confidence?: number | null;
};

export type TimelineTrack = {
  key: TimelineTrackKey;
  machineName: NeuroScoreMachineName;
  label: string;
  description: string;
  color: string;
  windows: TimelineTrackWindow[];
};

export type TimelineKeyMomentType =
  | 'hook_window'
  | 'event_boundary'
  | 'reward_ramp'
  | 'reveal_window'
  | 'cta_window'
  | 'dead_zone';

export type TimelineKeyMoment = {
  type: TimelineKeyMomentType;
  label: string;
  start_ms: number;
  end_ms: number;
  reason: string;
  color: string;
};

export const TRACK_ORDER: TimelineTrackKey[] = [
  'attention_arrest',
  'attentional_synchrony',
  'narrative_control',
  'blink_transport',
  'reward_anticipation',
  'boundary_encoding',
  'cta_reception',
  'au_friction'
];

const TRACK_META: Record<
  TimelineTrackKey,
  {
    machineName: NeuroScoreMachineName;
    label: string;
    description: string;
    color: string;
  }
> = {
  attention_arrest: {
    machineName: 'arrest_score',
    label: 'Attention / Arrest',
    description:
      'Claim-safe proxy for sustained viewer hold and attention continuity across key moments.',
    color: '#2f7dff'
  },
  attentional_synchrony: {
    machineName: 'attentional_synchrony_index',
    label: 'Attentional Synchrony',
    description:
      'Convergence estimate for whether viewers align on the same moment or focal target.',
    color: '#19c6ff'
  },
  narrative_control: {
    machineName: 'narrative_control_score',
    label: 'Narrative Control',
    description:
      'Cinematic-grammar diagnostic for how coherently edits guide understanding over time.',
    color: '#7cb8ff'
  },
  blink_transport: {
    machineName: 'blink_transport_score',
    label: 'Blink Transport',
    description:
      'Attentional gating proxy from blink suppression/rebound timing, not a biochemical meter.',
    color: '#58d4c1'
  },
  reward_anticipation: {
    machineName: 'reward_anticipation_index',
    label: 'Reward Anticipation',
    description:
      'Anticipatory pull proxy from setup-to-payoff dynamics without claiming direct neurochemical readout.',
    color: '#ff8f3d'
  },
  boundary_encoding: {
    machineName: 'boundary_encoding_score',
    label: 'Boundary Encoding',
    description:
      'Placement diagnostic for whether payload moments align with event boundaries likely to be chunked.',
    color: '#a485ff'
  },
  cta_reception: {
    machineName: 'cta_reception_score',
    label: 'CTA Reception',
    description:
      'Likelihood that the CTA lands while attention and narrative coherence remain supportive.',
    color: '#ffb347'
  },
  au_friction: {
    machineName: 'au_friction_score',
    label: 'AU Friction',
    description:
      'Diagnostic facial-action friction signal (AU-level), not an emotion truth engine.',
    color: '#f06292'
  }
};

export const DEFAULT_TIMELINE_TRACK_VISIBILITY: TimelineTrackVisibility = {
  attention_arrest: true,
  attentional_synchrony: true,
  narrative_control: true,
  blink_transport: true,
  reward_anticipation: true,
  boundary_encoding: true,
  cta_reception: true,
  au_friction: true
};

const KEY_MOMENT_COLORS: Record<TimelineKeyMomentType, string> = {
  hook_window: '#22c55e',
  event_boundary: '#64748b',
  reward_ramp: '#fb923c',
  reveal_window: '#8b5cf6',
  cta_window: '#facc15',
  dead_zone: '#ef4444'
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function normalizeWindow(
  durationMs: number,
  startMs: number,
  endMs: number,
  minimumMs = 250
): { start_ms: number; end_ms: number } | null {
  if (!Number.isFinite(durationMs) || durationMs <= 0) {
    return null;
  }

  const safeStart = Math.round(clamp(startMs, 0, durationMs));
  const boundedEnd = Math.round(clamp(endMs, 0, durationMs));
  const safeEnd = boundedEnd > safeStart ? boundedEnd : Math.min(durationMs, safeStart + minimumMs);

  if (safeEnd <= safeStart) {
    return null;
  }

  return {
    start_ms: safeStart,
    end_ms: safeEnd
  };
}

function pushWindow(
  windows: TimelineTrackWindow[],
  dedupe: Set<string>,
  durationMs: number,
  payload: {
    startMs: number;
    endMs: number;
    reason: string;
    source: string;
    score?: number | null;
    confidence?: number | null;
  }
): void {
  const normalized = normalizeWindow(durationMs, payload.startMs, payload.endMs);
  if (!normalized) {
    return;
  }
  const key = `${normalized.start_ms}:${normalized.end_ms}:${payload.reason}:${payload.source}`;
  if (dedupe.has(key)) {
    return;
  }
  dedupe.add(key);
  windows.push({
    start_ms: normalized.start_ms,
    end_ms: normalized.end_ms,
    reason: payload.reason,
    source: payload.source,
    score: payload.score ?? null,
    confidence: payload.confidence ?? null
  });
}

function resolveTrackWindows(readout: VideoReadout, trackKey: TimelineTrackKey): TimelineTrackWindow[] {
  const durationMs = readout.duration_ms;
  const windows: TimelineTrackWindow[] = [];
  const dedupe = new Set<string>();
  const meta = TRACK_META[trackKey];
  const neuroScore = readout.neuro_scores?.scores?.[meta.machineName];

  (neuroScore?.evidence_windows ?? []).forEach((window) => {
    pushWindow(windows, dedupe, durationMs, {
      startMs: window.start_ms,
      endMs: window.end_ms,
      reason: window.reason,
      source: 'neuro_score_contract',
      score: neuroScore?.scalar_value,
      confidence: neuroScore?.confidence
    });
  });

  if (trackKey === 'attention_arrest') {
    readout.segments.golden_scenes.forEach((segment) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: segment.start_video_time_ms,
        endMs: segment.end_video_time_ms,
        reason: segment.reason_codes[0] ?? 'Golden scene engagement window',
        source: 'segments.golden_scenes',
        score: segment.score ?? segment.magnitude,
        confidence: segment.confidence
      });
    });
    readout.segments.dead_zones.forEach((segment) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: segment.start_video_time_ms,
        endMs: segment.end_video_time_ms,
        reason: segment.reason_codes[0] ?? 'Dead zone / drop-off risk',
        source: 'segments.dead_zones',
        score: segment.score ?? segment.magnitude,
        confidence: segment.confidence
      });
    });
  }

  if (trackKey === 'attentional_synchrony') {
    (readout.aggregate_metrics?.attentional_synchrony?.segment_scores ?? []).forEach((segment) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: segment.start_ms,
        endMs: segment.end_ms,
        reason: segment.reason,
        source: 'aggregate_metrics.attentional_synchrony.segment_scores',
        score: segment.score,
        confidence: segment.confidence
      });
    });
  }

  if (trackKey === 'narrative_control') {
    (readout.aggregate_metrics?.narrative_control?.scene_scores ?? []).forEach((scene) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: scene.start_ms,
        endMs: scene.end_ms,
        reason: scene.summary,
        source: 'aggregate_metrics.narrative_control.scene_scores',
        score: scene.score,
        confidence: scene.confidence
      });
    });
  }

  if (trackKey === 'reward_anticipation') {
    (readout.aggregate_metrics?.reward_anticipation?.anticipation_ramps ?? []).forEach((window) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: window.start_ms,
        endMs: window.end_ms,
        reason: `Ramp: ${window.reason}`,
        source: 'aggregate_metrics.reward_anticipation.anticipation_ramps',
        score: window.score,
        confidence: window.confidence
      });
    });
    (readout.aggregate_metrics?.reward_anticipation?.payoff_windows ?? []).forEach((window) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: window.start_ms,
        endMs: window.end_ms,
        reason: `Payoff: ${window.reason}`,
        source: 'aggregate_metrics.reward_anticipation.payoff_windows',
        score: window.score,
        confidence: window.confidence
      });
    });
  }

  if (trackKey === 'cta_reception') {
    readout.context.cta_markers.forEach((cta) => {
      const startMs = cta.start_ms ?? cta.video_time_ms;
      const endMs = cta.end_ms ?? cta.video_time_ms + 1000;
      pushWindow(windows, dedupe, durationMs, {
        startMs,
        endMs,
        reason: cta.label ? `${cta.label} CTA window` : `${cta.cta_id} CTA window`,
        source: 'context.cta_markers'
      });
    });
  }

  if (trackKey === 'au_friction') {
    readout.segments.confusion_segments.forEach((segment) => {
      pushWindow(windows, dedupe, durationMs, {
        startMs: segment.start_video_time_ms,
        endMs: segment.end_video_time_ms,
        reason: segment.reason_codes[0] ?? 'AU friction / confusion diagnostic window',
        source: 'segments.confusion_segments',
        score: segment.score ?? segment.magnitude,
        confidence: segment.confidence
      });
    });
  }

  windows.sort((left, right) => left.start_ms - right.start_ms || left.end_ms - right.end_ms);
  return windows;
}

function findDiagnosticCard(
  diagnostics: ReadoutDiagnosticCard[] | undefined,
  cardType: ReadoutDiagnosticCard['card_type']
): ReadoutDiagnosticCard | undefined {
  return diagnostics?.find((card) => card.card_type === cardType);
}

function segmentReason(segment: ReadoutSegment, fallback: string): string {
  if (segment.reason_codes.length > 0) {
    return segment.reason_codes.join(', ');
  }
  return fallback;
}

export function buildTimelineTracks(readout: VideoReadout): TimelineTrack[] {
  return TRACK_ORDER.map((key) => {
    const meta = TRACK_META[key];
    return {
      key,
      machineName: meta.machineName,
      label: meta.label,
      description: meta.description,
      color: meta.color,
      windows: resolveTrackWindows(readout, key)
    };
  });
}

export function buildTimelineKeyMoments(readout: VideoReadout): TimelineKeyMoment[] {
  const moments: TimelineKeyMoment[] = [];
  const dedupe = new Set<string>();
  const durationMs = readout.duration_ms;

  const pushMoment = (
    type: TimelineKeyMomentType,
    startMs: number,
    endMs: number,
    reason: string,
    label: string
  ) => {
    const normalized = normalizeWindow(durationMs, startMs, endMs, type === 'event_boundary' ? 120 : 250);
    if (!normalized) {
      return;
    }
    const key = `${type}:${normalized.start_ms}:${normalized.end_ms}:${reason}`;
    if (dedupe.has(key)) {
      return;
    }
    dedupe.add(key);
    moments.push({
      type,
      label,
      start_ms: normalized.start_ms,
      end_ms: normalized.end_ms,
      reason,
      color: KEY_MOMENT_COLORS[type]
    });
  };

  const hookCard = findDiagnosticCard(readout.diagnostics, 'hook_strength');
  if (hookCard) {
    pushMoment(
      'hook_window',
      hookCard.start_video_time_ms,
      hookCard.end_video_time_ms,
      hookCard.why_flagged,
      'Hook window'
    );
  } else {
    pushMoment(
      'hook_window',
      0,
      Math.min(durationMs, 3000),
      'Default opening hook window (first 1-3 seconds).',
      'Hook window'
    );
  }

  readout.context.scenes
    .filter((scene) => scene.start_ms > 0)
    .forEach((scene) => {
      pushMoment(
        'event_boundary',
        scene.start_ms,
        scene.start_ms,
        scene.label ? `${scene.label} boundary` : `Scene ${scene.scene_index + 1} boundary`,
        'Event boundary'
      );
    });

  readout.context.cuts
    .filter((cut) => cut.start_ms > 0)
    .forEach((cut) => {
      pushMoment(
        'event_boundary',
        cut.start_ms,
        cut.start_ms,
        `Cut boundary ${cut.cut_id}`,
        'Event boundary'
      );
    });

  (readout.aggregate_metrics?.reward_anticipation?.anticipation_ramps ?? []).forEach((ramp) => {
    pushMoment('reward_ramp', ramp.start_ms, ramp.end_ms, ramp.reason, 'Reward ramp');
  });

  (readout.aggregate_metrics?.narrative_control?.reveal_structure_bonuses ?? []).forEach((moment) => {
    pushMoment('reveal_window', moment.start_ms, moment.end_ms, moment.reason, 'Reveal window');
  });

  readout.context.cta_markers.forEach((cta) => {
    const startMs = cta.start_ms ?? cta.video_time_ms;
    const endMs = cta.end_ms ?? cta.video_time_ms + 1000;
    pushMoment(
      'cta_window',
      startMs,
      endMs,
      cta.label ? `${cta.label} CTA window` : `${cta.cta_id} CTA window`,
      'CTA window'
    );
  });

  readout.segments.dead_zones.forEach((segment) => {
    pushMoment(
      'dead_zone',
      segment.start_video_time_ms,
      segment.end_video_time_ms,
      segmentReason(segment, 'Drop-off risk segment'),
      'Dead zone / drop-off risk'
    );
  });

  moments.sort((left, right) => left.start_ms - right.start_ms || left.end_ms - right.end_ms);
  return moments;
}
