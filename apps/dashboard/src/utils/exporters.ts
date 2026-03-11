import type { ReadoutExportPackage, VideoReadout } from '../types';
import { mapReadoutToTimeline } from './readout';

function downloadBlob(fileName: string, content: string, contentType: string): void {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

type ExportBuildOptions = {
  generatedAt?: string;
};

type ReadoutExportMetadata = {
  schema_version: string;
  generated_at: string;
  video_id: string;
  variant_id: string | null;
  session_id: string | null;
  aggregate: boolean;
  duration_ms: number;
  timebase: {
    window_ms: number;
    step_ms: number;
  };
};

type ReadoutJsonExport = {
  schema_version: string;
  metadata: ReadoutExportMetadata;
  context: VideoReadout['context'];
  segments: VideoReadout['segments'];
  labels: {
    annotations: VideoReadout['labels']['annotations'];
    annotation_summary: VideoReadout['labels']['annotation_summary'] | null;
    survey_summary: VideoReadout['labels']['survey_summary'] | null;
  };
  quality: VideoReadout['quality'];
  diagnostics: VideoReadout['diagnostics'];
  aggregate_metrics: VideoReadout['aggregate_metrics'] | null;
  neuro_scores: VideoReadout['neuro_scores'] | null;
  product_rollups: VideoReadout['product_rollups'] | null;
  legacy_score_adapters: VideoReadout['legacy_score_adapters'];
};

type EditSuggestionsStub = {
  schema_version: string;
  metadata: ReadoutExportMetadata;
  edit_suggestions: {
    candidate_trims: Array<{
      start_video_time_ms: number;
      end_video_time_ms: number;
      scene_id: string | null;
      confidence: number | null;
      reason_codes: string[];
      source_metric: string;
    }>;
    candidate_reorder_suggestions: Array<{
      scene_id: string | null;
      current_start_video_time_ms: number;
      suggested_target_start_video_time_ms: number;
      confidence: number | null;
      reason: string;
    }>;
    cta_timing_suggestion:
      | {
          cta_id: string;
          cta_video_time_ms: number;
          reward_peak_video_time_ms: number | null;
          delta_to_peak_ms: number | null;
          alignment: 'pre_peak' | 'post_peak' | 'near_peak' | 'unknown';
          suggestion: string;
        }
      | null;
  };
};

function getMetadata(readout: VideoReadout, options?: ExportBuildOptions): ReadoutExportMetadata {
  return {
    schema_version: readout.schema_version,
    generated_at: options?.generatedAt ?? new Date().toISOString(),
    video_id: readout.video_id,
    variant_id: readout.variant_id ?? null,
    session_id: readout.session_id ?? null,
    aggregate: readout.aggregate,
    duration_ms: readout.duration_ms,
    timebase: {
      window_ms: readout.timebase.window_ms,
      step_ms: readout.timebase.step_ms
    }
  };
}

function toCsvCell(value: string): string {
  return `"${value.split('"').join('""')}"`;
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '';
  }
  return value.toFixed(6);
}

function getTopRewardPeak(
  readout: VideoReadout
): { video_time_ms: number; value: number } | null {
  let best: { video_time_ms: number; value: number } | null = null;
  for (const point of readout.traces.reward_proxy) {
    if (point.value === null || point.value === undefined) {
      continue;
    }
    if (!best || point.value > best.value) {
      best = { video_time_ms: point.video_time_ms, value: point.value };
    }
  }
  return best;
}

export function buildReadoutCsv(
  readout: VideoReadout,
  selectedAuNames: string[],
  options?: ExportBuildOptions
): string {
  const metadata = getMetadata(readout, options);
  const points = mapReadoutToTimeline(readout);
  const header = [
    'schema_version',
    'generated_at',
    'video_id',
    'variant_id',
    'session_id',
    'aggregate',
    'duration_ms',
    'window_ms',
    'step_ms',
    'video_time_ms',
    'second',
    'scene_id',
    'cut_id',
    'cta_id',
    'attention_score',
    'attention_velocity',
    'blink_rate',
    'blink_inhibition',
    'reward_proxy',
    'valence_proxy',
    'arousal_proxy',
    'novelty_proxy',
    'tracking_confidence',
    ...selectedAuNames.map((au) => `au_${au}`)
  ];

  const rows = points.map((point) => [
    metadata.schema_version,
    metadata.generated_at,
    metadata.video_id,
    metadata.variant_id ?? '',
    metadata.session_id ?? '',
    String(metadata.aggregate),
    String(metadata.duration_ms),
    String(metadata.timebase.window_ms),
    String(metadata.timebase.step_ms),
    String(point.tMs),
    point.tSec.toFixed(3),
    point.sceneId ?? '',
    point.cutId ?? '',
    point.ctaId ?? '',
    formatNumber(point.attentionScore),
    formatNumber(point.attentionVelocity),
    formatNumber(point.blinkRate),
    formatNumber(point.blinkInhibition),
    formatNumber(point.rewardProxy),
    formatNumber(point.valenceProxy),
    formatNumber(point.arousalProxy),
    formatNumber(point.noveltyProxy),
    formatNumber(point.trackingConfidence),
    ...selectedAuNames.map((au) => formatNumber(point.auValues[au]))
  ]);

  return [header, ...rows].map((cells) => cells.map(toCsvCell).join(',')).join('\n');
}

export function buildReadoutJsonPayload(
  readout: VideoReadout,
  options?: ExportBuildOptions
): ReadoutJsonExport {
  return {
    schema_version: readout.schema_version,
    metadata: getMetadata(readout, options),
    context: readout.context,
    segments: readout.segments,
    labels: {
      annotations: readout.labels.annotations,
      annotation_summary: readout.labels.annotation_summary ?? null,
      survey_summary: readout.labels.survey_summary ?? null
    },
    quality: readout.quality,
    diagnostics: readout.diagnostics ?? [],
    aggregate_metrics: readout.aggregate_metrics ?? null,
    neuro_scores: readout.neuro_scores ?? null,
    product_rollups: readout.product_rollups ?? null,
    legacy_score_adapters: readout.legacy_score_adapters ?? []
  };
}

export function buildEditSuggestionsStubPayload(
  readout: VideoReadout,
  options?: ExportBuildOptions
): EditSuggestionsStub {
  const metadata = getMetadata(readout, options);
  const deadZones = readout.segments.dead_zones ?? [];
  const goldenScenes = readout.segments.golden_scenes ?? [];
  const scenes = [...readout.context.scenes].sort((a, b) => a.start_ms - b.start_ms);
  const firstScene = scenes[0];
  const topGolden = [...goldenScenes].sort((a, b) => b.magnitude - a.magnitude)[0];
  const rewardPeak = getTopRewardPeak(readout);
  const ctaMarkers = readout.context.cta_markers ?? [];
  const cta = ctaMarkers[0];
  const nearPeakThresholdMs = Math.max(readout.timebase.step_ms, readout.timebase.window_ms);

  const ctaTimingSuggestion = (() => {
    if (!cta || !rewardPeak) {
      return {
        cta_id: cta?.cta_id ?? 'unknown',
        cta_video_time_ms: cta?.video_time_ms ?? 0,
        reward_peak_video_time_ms: rewardPeak?.video_time_ms ?? null,
        delta_to_peak_ms: null,
        alignment: 'unknown' as const,
        suggestion:
          !cta
            ? 'No CTA marker found in readout context. Add CTA timing metadata before optimization.'
            : 'Reward peak unavailable in current payload; review trace quality before CTA timing edits.'
      };
    }
    const delta = cta.video_time_ms - rewardPeak.video_time_ms;
    if (Math.abs(delta) <= nearPeakThresholdMs) {
      return {
        cta_id: cta.cta_id,
        cta_video_time_ms: cta.video_time_ms,
        reward_peak_video_time_ms: rewardPeak.video_time_ms,
        delta_to_peak_ms: delta,
        alignment: 'near_peak' as const,
        suggestion: 'CTA timing is close to reward peak. Keep current placement for A/B validation.'
      };
    }
    if (delta > 0) {
      return {
        cta_id: cta.cta_id,
        cta_video_time_ms: cta.video_time_ms,
        reward_peak_video_time_ms: rewardPeak.video_time_ms,
        delta_to_peak_ms: delta,
        alignment: 'post_peak' as const,
        suggestion: 'CTA appears after reward peak. Test moving CTA earlier toward the peak window.'
      };
    }
    return {
      cta_id: cta.cta_id,
      cta_video_time_ms: cta.video_time_ms,
      reward_peak_video_time_ms: rewardPeak.video_time_ms,
      delta_to_peak_ms: delta,
      alignment: 'pre_peak' as const,
      suggestion: 'CTA appears before reward peak. Test delaying CTA closer to the strongest response moment.'
    };
  })();

  return {
    schema_version: readout.schema_version,
    metadata,
    edit_suggestions: {
      candidate_trims: deadZones.map((segment) => ({
        start_video_time_ms: segment.start_video_time_ms,
        end_video_time_ms: segment.end_video_time_ms,
        scene_id: segment.scene_id ?? null,
        confidence: segment.confidence ?? null,
        reason_codes: segment.reason_codes,
        source_metric: 'dead_zone'
      })),
      candidate_reorder_suggestions:
        topGolden && firstScene && topGolden.start_video_time_ms > firstScene.end_ms
          ? [
              {
                scene_id: topGolden.scene_id ?? null,
                current_start_video_time_ms: topGolden.start_video_time_ms,
                suggested_target_start_video_time_ms: firstScene.start_ms,
                confidence: topGolden.confidence ?? null,
                reason:
                  'Top golden scene occurs after the opening window. Evaluate moving a related scene/cut earlier.'
              }
            ]
          : [],
      cta_timing_suggestion: ctaTimingSuggestion
    }
  };
}

export function exportReadoutCsv(
  readout: VideoReadout,
  selectedAuNames: string[],
  options?: ExportBuildOptions
): void {
  const content = buildReadoutCsv(readout, selectedAuNames, options);
  downloadBlob(`${readout.video_id}-readout-traces.csv`, content, 'text/csv;charset=utf-8;');
}

export function exportReadoutJson(readout: VideoReadout, options?: ExportBuildOptions): void {
  const readoutJson = buildReadoutJsonPayload(readout, options);
  const editSuggestionsStub = buildEditSuggestionsStubPayload(readout, options);
  downloadBlob(
    `${readout.video_id}-readout.json`,
    JSON.stringify(readoutJson, null, 2),
    'application/json;charset=utf-8;'
  );
  downloadBlob(
    `${readout.video_id}-edit-suggestions.stub.json`,
    JSON.stringify(editSuggestionsStub, null, 2),
    'application/json;charset=utf-8;'
  );
}

export function exportReadoutPackage(videoId: string, payload: ReadoutExportPackage): void {
  downloadBlob(
    `${videoId}-readout-timepoints.csv`,
    payload.per_timepoint_csv,
    'text/csv;charset=utf-8;'
  );
  downloadBlob(
    `${videoId}-readout-export.json`,
    JSON.stringify(payload.readout_json, null, 2),
    'application/json;charset=utf-8;'
  );
  downloadBlob(
    `${videoId}-readout-compact-report.json`,
    JSON.stringify(payload.compact_report, null, 2),
    'application/json;charset=utf-8;'
  );
  if (payload.edit_suggestions_stub) {
    downloadBlob(
      `${videoId}-edit-suggestions.stub.json`,
      JSON.stringify(payload.edit_suggestions_stub, null, 2),
      'application/json;charset=utf-8;'
    );
  }
}
