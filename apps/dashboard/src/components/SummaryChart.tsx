import { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';

type MarkerType =
  | 'engaging_moment'
  | 'confusing_moment'
  | 'stop_watching_moment'
  | 'cta_landed_moment';

type TelemetryKind = 'pause' | 'seek' | 'abandonment';

type LayerVisibility = {
  attentionScore: boolean;
  attentionVelocity: boolean;
  blinkRate: boolean;
  blinkInhibition: boolean;
  rewardProxy: boolean;
  valenceProxy: boolean;
  arousalProxy: boolean;
  noveltyProxy: boolean;
  trackingConfidence: boolean;
};

type LegacyTimelinePoint = {
  tMs: number;
  tSec: number;
  attention?: number;
  blinkRate?: number;
  blinkInhibition?: number;
  rewardProxy?: number | null;
  sceneId?: string | null;
  cutId?: string | null;
  ctaId?: string | null;
  au12?: number;
  au6?: number;
  au4?: number;
};

type ReadoutTimelinePointLike = {
  tMs: number;
  tSec: number;
  sceneId?: string | null;
  cutId?: string | null;
  ctaId?: string | null;
  attentionScore?: number | null;
  attentionScoreCiLow?: number | null;
  attentionScoreCiHigh?: number | null;
  attentionVelocity?: number | null;
  blinkRate?: number | null;
  blinkInhibition?: number | null;
  rewardProxy?: number | null;
  rewardProxyCiLow?: number | null;
  rewardProxyCiHigh?: number | null;
  predictedAttentionScore?: number | null;
  predictedRewardProxy?: number | null;
  predictedBlinkInhibition?: number | null;
  valenceProxy?: number | null;
  arousalProxy?: number | null;
  noveltyProxy?: number | null;
  trackingConfidence?: number | null;
  auValues?: Record<string, number | null | undefined>;
};

type SceneLike = {
  scene_index: number;
  start_ms: number;
  end_ms: number;
  label?: string | null;
};

type CutLike = {
  cut_id: string;
  start_ms: number;
};

type CtaLike = {
  cta_id: string;
  video_time_ms: number;
  start_ms?: number | null;
  end_ms?: number | null;
  label?: string | null;
};

type AnnotationOverlayLike = {
  marker_type: MarkerType;
  video_time_ms: number;
  count: number;
};

type TelemetryOverlayLike = {
  kind: TelemetryKind;
  video_time_ms: number;
  count: number;
};

type ConfidenceWindowLike = {
  startSec: number;
  endSec: number;
};

type SummaryChartProps = {
  points: Array<LegacyTimelinePoint | ReadoutTimelinePointLike>;
  scenes: SceneLike[];
  cuts?: CutLike[];
  ctaMarkers?: CtaLike[];
  annotationOverlays?: AnnotationOverlayLike[];
  telemetryOverlays?: TelemetryOverlayLike[];
  isAggregateView?: boolean;
  availableAuNames?: string[];
  selectedAuNames?: string[];
  layerVisibility?: Partial<LayerVisibility>;
  lowConfidenceWindows?: ConfidenceWindowLike[];
  showPredictedOverlay?: boolean;
  cursorSec: number;
  onSeek: (seconds: number) => void;
};

type DotProps = {
  cx?: number;
  cy?: number;
  payload?: { tSec?: number };
  onSeek: (seconds: number) => void;
};

type TooltipProps = {
  active?: boolean;
  payload?: Array<{ payload: Record<string, unknown> }>;
  label?: number | string;
  availableAuNames: string[];
};

type ChartRow = {
  tMs: number;
  tSec: number;
  sceneId: string | null;
  cutId: string | null;
  ctaId: string | null;
  attentionScore: number | null;
  attentionScoreCiLow: number | null;
  attentionScoreCiHigh: number | null;
  attentionScoreCiBand: number | null;
  attentionVelocity: number | null;
  blinkRate: number | null;
  blinkInhibition: number | null;
  rewardProxy: number | null;
  rewardProxyCiLow: number | null;
  rewardProxyCiHigh: number | null;
  rewardProxyCiBand: number | null;
  predictedAttentionScore: number | null;
  predictedRewardProxy: number | null;
  predictedBlinkInhibition: number | null;
  valenceProxy: number | null;
  arousalProxy: number | null;
  noveltyProxy: number | null;
  trackingConfidence: number | null;
  [key: string]: string | number | null;
};

type ChartClickState = {
  activeLabel?: number | string;
  chartX?: number;
  offset?: {
    left?: number;
    width?: number;
  };
};

const defaultLayerVisibility: LayerVisibility = {
  attentionScore: true,
  attentionVelocity: true,
  blinkRate: true,
  blinkInhibition: true,
  rewardProxy: true,
  valenceProxy: false,
  arousalProxy: false,
  noveltyProxy: false,
  trackingConfidence: true
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function pointField(point: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = asNumber(point[key]);
    if (value !== null) {
      return value;
    }
  }
  return null;
}

function pointString(point: Record<string, unknown>, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = point[key];
    if (typeof value === 'string' && value.length > 0) {
      return value;
    }
  }
  return null;
}

function AttentionDot({ cx, cy, payload, onSeek }: DotProps) {
  if (cx === undefined || cy === undefined || payload?.tSec === undefined) {
    return <g />;
  }
  return (
    <circle
      cx={cx}
      cy={cy}
      r={4}
      fill="#2f7dff"
      stroke="#080b0f"
      strokeWidth={1}
      style={{ cursor: 'pointer' }}
      onClick={() => onSeek(payload.tSec as number)}
      data-testid={`attention-point-${payload.tSec}`}
    />
  );
}

function TraceTooltip({ active, payload, label, availableAuNames }: TooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const row = payload[0].payload as ChartRow;

  return (
    <div
      style={{
        background: '#0d1117',
        border: '1px solid rgba(255,255,255,0.13)',
        borderRadius: 8,
        padding: 10,
        minWidth: 260
      }}
      data-testid="trace-hover-tooltip"
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>t={label}s</div>
      <div style={{ fontSize: 12, color: '#8a97a8' }}>
        scene: {row.sceneId ?? 'n/a'} | cut: {row.cutId ?? 'n/a'} | cta: {row.ctaId ?? 'n/a'}
      </div>
      <div style={{ marginTop: 8, display: 'grid', gap: 3, fontSize: 12, color: '#e8edf3' }}>
        <div>attention_score: {row.attentionScore ?? 'n/a'}</div>
        <div>attention_velocity: {row.attentionVelocity ?? 'n/a'}</div>
        <div>blink_rate: {row.blinkRate ?? 'n/a'}</div>
        <div>blink_inhibition: {row.blinkInhibition ?? 'n/a'}</div>
        <div>reward_proxy: {row.rewardProxy ?? 'n/a'}</div>
        <div>pred_attention_score: {row.predictedAttentionScore ?? 'n/a'}</div>
        <div>pred_blink_inhibition: {row.predictedBlinkInhibition ?? 'n/a'}</div>
        <div>pred_reward_proxy: {row.predictedRewardProxy ?? 'n/a'}</div>
        <div>tracking_confidence: {row.trackingConfidence ?? 'n/a'}</div>
        {availableAuNames.map((auName) => (
          <div key={auName}>
            {auName}: {row[`au_${auName}`] ?? 'n/a'}
          </div>
        ))}
      </div>
    </div>
  );
}

const markerPalette: Record<MarkerType, string> = {
  engaging_moment: '#16a34a',
  confusing_moment: '#d97706',
  stop_watching_moment: '#dc2626',
  cta_landed_moment: '#7c3aed'
};

const markerLabel: Record<MarkerType, string> = {
  engaging_moment: 'Engaging',
  confusing_moment: 'Confusing',
  stop_watching_moment: 'Stop',
  cta_landed_moment: 'CTA'
};

const telemetryPalette: Record<TelemetryKind, string> = {
  pause: '#f59e0b',
  seek: '#0ea5e9',
  abandonment: '#dc2626'
};

const telemetryLabel: Record<TelemetryKind, string> = {
  pause: 'Pause',
  seek: 'Seek',
  abandonment: 'Abandon'
};

export default function SummaryChart({
  points,
  scenes,
  cuts = [],
  ctaMarkers = [],
  annotationOverlays = [],
  telemetryOverlays = [],
  isAggregateView = false,
  availableAuNames = [],
  selectedAuNames = [],
  layerVisibility = {},
  lowConfidenceWindows = [],
  showPredictedOverlay = false,
  cursorSec,
  onSeek
}: SummaryChartProps) {
  const mergedVisibility: LayerVisibility = { ...defaultLayerVisibility, ...layerVisibility };

  const chartData = useMemo<ChartRow[]>(
    () =>
      points.map((rawPoint) => {
        const point = rawPoint as unknown as Record<string, unknown>;
        const tMs = pointField(point, 'tMs', 'video_time_ms', 'bucket_start_ms') ?? 0;
        const tSecRaw = pointField(point, 'tSec');
        const tSec = tSecRaw ?? tMs / 1000;

        const attentionScore = pointField(point, 'attentionScore', 'attention');
        const blinkRate = pointField(point, 'blinkRate', 'mean_rolling_blink_rate', 'blink_rate');
        const blinkInhibition = pointField(
          point,
          'blinkInhibition',
          'mean_blink_inhibition_score',
          'blink_inhibition'
        );
        const rewardProxy = pointField(point, 'rewardProxy', 'reward_proxy', 'mean_reward_proxy');
        const predictedAttentionScore = pointField(
          point,
          'predictedAttentionScore',
          'pred_attention_score',
          'predicted_attention_score'
        );
        const predictedRewardProxy = pointField(
          point,
          'predictedRewardProxy',
          'pred_reward_proxy',
          'predicted_reward_proxy'
        );
        const predictedBlinkInhibition = pointField(
          point,
          'predictedBlinkInhibition',
          'pred_blink_inhibition',
          'predicted_blink_inhibition'
        );
        const trackingConfidence = pointField(
          point,
          'trackingConfidence',
          'mean_quality_confidence',
          'qualityConfidence'
        );

        const row: ChartRow = {
          tMs,
          tSec: Number(tSec.toFixed(3)),
          sceneId: pointString(point, 'sceneId', 'scene_id'),
          cutId: pointString(point, 'cutId', 'cut_id'),
          ctaId: pointString(point, 'ctaId', 'cta_id'),
          attentionScore,
          attentionScoreCiLow: pointField(point, 'attentionScoreCiLow', 'attention_score_ci_low'),
          attentionScoreCiHigh: pointField(point, 'attentionScoreCiHigh', 'attention_score_ci_high'),
          attentionScoreCiBand: null,
          attentionVelocity: pointField(point, 'attentionVelocity', 'attention_velocity'),
          blinkRate,
          blinkInhibition,
          rewardProxy,
          rewardProxyCiLow: pointField(point, 'rewardProxyCiLow', 'reward_proxy_ci_low'),
          rewardProxyCiHigh: pointField(point, 'rewardProxyCiHigh', 'reward_proxy_ci_high'),
          rewardProxyCiBand: null,
          predictedAttentionScore,
          predictedRewardProxy,
          predictedBlinkInhibition,
          valenceProxy: pointField(point, 'valenceProxy', 'valence_proxy'),
          arousalProxy: pointField(point, 'arousalProxy', 'arousal_proxy'),
          noveltyProxy: pointField(point, 'noveltyProxy', 'novelty_proxy'),
          trackingConfidence
        };

        if (
          row.attentionScoreCiLow !== null &&
          row.attentionScoreCiHigh !== null &&
          row.attentionScoreCiHigh >= row.attentionScoreCiLow
        ) {
          row.attentionScoreCiBand = row.attentionScoreCiHigh - row.attentionScoreCiLow;
        }

        if (
          row.rewardProxyCiLow !== null &&
          row.rewardProxyCiHigh !== null &&
          row.rewardProxyCiHigh >= row.rewardProxyCiLow
        ) {
          row.rewardProxyCiBand = row.rewardProxyCiHigh - row.rewardProxyCiLow;
        }

        const auValues = point.auValues as Record<string, number | null | undefined> | undefined;
        availableAuNames.forEach((auName) => {
          const direct = pointField(point, `au_${auName}`, auName.toLowerCase(), auName);
          if (direct !== null) {
            row[`au_${auName}`] = direct;
            return;
          }
          if (auValues) {
            const fallback = auValues[auName];
            row[`au_${auName}`] = typeof fallback === 'number' ? fallback : null;
            return;
          }
          if (auName === 'AU12') {
            row[`au_${auName}`] = pointField(point, 'au12');
            return;
          }
          if (auName === 'AU6') {
            row[`au_${auName}`] = pointField(point, 'au6');
            return;
          }
          if (auName === 'AU4') {
            row[`au_${auName}`] = pointField(point, 'au4');
            return;
          }
          row[`au_${auName}`] = null;
        });

        return row;
      }),
    [availableAuNames, points]
  );

  const sceneRegions = useMemo(
    () =>
      scenes.map((scene) => ({
        x1: scene.start_ms / 1000,
        x2: scene.end_ms / 1000
      })),
    [scenes]
  );

  const ctaRegions = useMemo(
    () =>
      ctaMarkers
        .map((marker) => {
          const startMs = (marker.start_ms ?? marker.video_time_ms) || 0;
          const fallbackEndMs = marker.video_time_ms + 1000;
          const endMsRaw = marker.end_ms ?? fallbackEndMs;
          const endMs = endMsRaw > startMs ? endMsRaw : startMs + 1000;
          return {
            ctaId: marker.cta_id,
            x1: startMs / 1000,
            x2: endMs / 1000
          };
        })
        .filter((item): item is { ctaId: string; x1: number; x2: number } => Boolean(item)),
    [ctaMarkers]
  );

  const timeRange = useMemo(() => {
    if (chartData.length === 0) {
      return { minSec: 0, maxSec: 0 };
    }
    return {
      minSec: chartData[0].tSec,
      maxSec: chartData[chartData.length - 1].tSec
    };
  }, [chartData]);

  const hasPredictedAttention = useMemo(
    () => chartData.some((row) => row.predictedAttentionScore !== null),
    [chartData]
  );
  const hasPredictedRewardProxy = useMemo(
    () => chartData.some((row) => row.predictedRewardProxy !== null),
    [chartData]
  );
  const hasPredictedBlinkInhibition = useMemo(
    () => chartData.some((row) => row.predictedBlinkInhibition !== null),
    [chartData]
  );

  return (
    <div style={{ width: '100%', height: 480 }} data-testid="summary-chart">
      <ResponsiveContainer>
        <ComposedChart
          data={chartData}
          margin={{ top: 16, right: 24, left: 8, bottom: 12 }}
          onClick={(state) => {
            const clickState = state as ChartClickState | undefined;
            const activeLabel = clickState?.activeLabel;
            if (typeof activeLabel === 'number') {
              onSeek(activeLabel);
              return;
            }

            if (
              clickState?.chartX === undefined ||
              clickState?.offset?.left === undefined ||
              clickState?.offset?.width === undefined ||
              clickState.offset.width <= 0
            ) {
              return;
            }

            const relativeX = (clickState.chartX - clickState.offset.left) / clickState.offset.width;
            const normalized = clamp(relativeX, 0, 1);
            const targetSec = timeRange.minSec + normalized * (timeRange.maxSec - timeRange.minSec);
            onSeek(targetSec);
          }}
        >
          <CartesianGrid strokeDasharray="4 4" stroke="rgba(138,151,168,0.22)" />
          <XAxis dataKey="tSec" tickFormatter={(value) => `${value}s`} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
          <YAxis yAxisId="engagement" domain={[0, 100]} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
          <YAxis yAxisId="signals" orientation="right" domain={['auto', 'auto']} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
          <YAxis yAxisId="velocity" orientation="right" domain={['auto', 'auto']} hide />
          <Tooltip content={<TraceTooltip availableAuNames={availableAuNames} />} cursor={{ stroke: '#c8f031', strokeWidth: 1, strokeDasharray: '4 3' }} />
          <Legend wrapperStyle={{ color: '#8a8895', fontSize: 12 }} />

          {sceneRegions.map((scene, index) => (
            <ReferenceArea
              key={`scene-${scene.x1}-${scene.x2}`}
              x1={scene.x1}
              x2={scene.x2}
              yAxisId="engagement"
              fill={index % 2 === 0 ? '#1b2637' : '#111b29'}
              fillOpacity={0.34}
              ifOverflow="extendDomain"
              data-testid={`scene-band-${index}`}
            />
          ))}
          {lowConfidenceWindows.map((window, index) => (
            <ReferenceArea
              key={`low-confidence-${window.startSec}-${window.endSec}-${index}`}
              x1={window.startSec}
              x2={window.endSec}
              yAxisId="engagement"
              fill="#fda4af"
              fillOpacity={0.18}
              ifOverflow="extendDomain"
              data-testid="low-confidence-window"
            />
          ))}
          {ctaRegions.map((region, index) => (
            <ReferenceArea
              key={`cta-region-${region.ctaId}-${region.x1}-${region.x2}-${index}`}
              x1={region.x1}
              x2={region.x2}
              yAxisId="engagement"
              fill="#00e5ff"
              fillOpacity={0.15}
              ifOverflow="extendDomain"
              data-testid={`cta-region-window-${index}`}
            />
          ))}
          {scenes.map((scene) => (
            <ReferenceLine
              key={`scene-boundary-${scene.scene_index}-${scene.start_ms}`}
              x={scene.start_ms / 1000}
              yAxisId="engagement"
              stroke="#4a5a6e"
              strokeDasharray="1 6"
              label={{
                value: scene.label ?? `Scene ${scene.scene_index + 1}`,
                position: 'insideTop',
                fill: '#8a97a8'
              }}
              data-testid={`scene-boundary-${scene.scene_index}`}
            />
          ))}
          {cuts.map((cut) => (
            <ReferenceLine
              key={`cut-${cut.cut_id}-${cut.start_ms}`}
              x={cut.start_ms / 1000}
              yAxisId="engagement"
              stroke="#2c3a4c"
              strokeDasharray="3 4"
              label={{ value: cut.cut_id, position: 'insideBottomLeft', fill: '#6f8197' }}
              data-testid={`cut-marker-${cut.cut_id}`}
            />
          ))}
          {ctaMarkers.map((cta) => (
            <ReferenceLine
              key={`cta-${cta.cta_id}-${cta.video_time_ms}`}
              x={cta.video_time_ms / 1000}
              yAxisId="engagement"
              stroke="#ffb347"
              strokeDasharray="8 3"
              label={{
                value: cta.label ? `${cta.label} (${cta.cta_id})` : cta.cta_id,
                position: 'insideTopRight',
                fill: '#ffb347'
              }}
              data-testid={`cta-marker-${cta.cta_id}`}
            />
          ))}
          {annotationOverlays.map((annotation, index) => (
            <ReferenceLine
              key={`annotation-overlay-${annotation.marker_type}-${annotation.video_time_ms}-${index}`}
              x={annotation.video_time_ms / 1000}
              yAxisId="engagement"
              stroke={markerPalette[annotation.marker_type]}
              strokeWidth={annotation.count > 1 ? 2.5 : 1.5}
              strokeDasharray="2 4"
              label={{
                value:
                  isAggregateView || annotation.count > 1
                    ? `${markerLabel[annotation.marker_type]} x${annotation.count}`
                    : markerLabel[annotation.marker_type],
                position: 'insideBottomRight',
                fill: markerPalette[annotation.marker_type]
              }}
              data-testid={`annotation-marker-${annotation.marker_type}-${index}`}
            />
          ))}
          {telemetryOverlays.map((telemetry, index) => (
            <ReferenceLine
              key={`telemetry-overlay-${telemetry.kind}-${telemetry.video_time_ms}-${index}`}
              x={telemetry.video_time_ms / 1000}
              yAxisId="engagement"
              stroke={telemetryPalette[telemetry.kind]}
              strokeWidth={telemetry.count > 1 ? 2.6 : 1.8}
              strokeDasharray={telemetry.kind === 'abandonment' ? '1 2' : '5 3'}
              label={{
                value:
                  isAggregateView || telemetry.count > 1
                    ? `${telemetryLabel[telemetry.kind]} x${telemetry.count}`
                    : telemetryLabel[telemetry.kind],
                position: telemetry.kind === 'abandonment' ? 'insideTopLeft' : 'insideBottomLeft',
                fill: telemetryPalette[telemetry.kind]
              }}
              data-testid={`telemetry-marker-${telemetry.kind}-${index}`}
            />
          ))}
          <ReferenceLine
            x={cursorSec}
            yAxisId="engagement"
            stroke="#ff4d6d"
            strokeDasharray="4 4"
            label={{ value: 'Now', position: 'insideTopRight', fill: '#ff4d6d' }}
          />

          {isAggregateView && mergedVisibility.attentionScore ? (
            <>
              <Area
                yAxisId="engagement"
                type="monotone"
                dataKey="attentionScoreCiLow"
                stackId="attention-ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                legendType="none"
              />
              <Area
                yAxisId="engagement"
                type="monotone"
                dataKey="attentionScoreCiBand"
                stackId="attention-ci"
                stroke="none"
                fill="#00e5ff"
                fillOpacity={0.12}
                name="attention_score_ci"
                isAnimationActive={false}
                data-testid="attention-ci-band"
              />
            </>
          ) : null}

          {isAggregateView && mergedVisibility.rewardProxy ? (
            <>
              <Area
                yAxisId="engagement"
                type="monotone"
                dataKey="rewardProxyCiLow"
                stackId="reward-ci"
                stroke="none"
                fill="transparent"
                isAnimationActive={false}
                legendType="none"
              />
              <Area
                yAxisId="engagement"
                type="monotone"
                dataKey="rewardProxyCiBand"
                stackId="reward-ci"
                stroke="none"
                fill="#ffb347"
                fillOpacity={0.12}
                name="reward_proxy_ci"
                isAnimationActive={false}
                data-testid="reward-ci-band"
              />
            </>
          ) : null}

          {mergedVisibility.attentionScore ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="attentionScore"
              name="attention_score"
              stroke="#2f7dff"
              strokeWidth={2.5}
              dot={(props) => <AttentionDot {...props} onSeek={onSeek} />}
              activeDot={{ r: 6 }}
              connectNulls
            />
          ) : null}
          {showPredictedOverlay && mergedVisibility.attentionScore && hasPredictedAttention ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="predictedAttentionScore"
              name="pred_attention_score"
              stroke="#7db3ff"
              strokeDasharray="6 3"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.attentionVelocity ? (
            <Line
              yAxisId="velocity"
              type="monotone"
              dataKey="attentionVelocity"
              name="attention_velocity"
              stroke="#8da2ff"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.blinkRate ? (
            <Line
              yAxisId="signals"
              type="monotone"
              dataKey="blinkRate"
              name="blink_rate"
              stroke="#ff4d6d"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.blinkInhibition ? (
            <Line
              yAxisId="signals"
              type="monotone"
              dataKey="blinkInhibition"
              name="blink_inhibition"
              stroke="#58d4c1"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}
          {showPredictedOverlay && mergedVisibility.blinkInhibition && hasPredictedBlinkInhibition ? (
            <Line
              yAxisId="signals"
              type="monotone"
              dataKey="predictedBlinkInhibition"
              name="pred_blink_inhibition"
              stroke="#9af2e5"
              strokeDasharray="6 3"
              strokeWidth={1.8}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.rewardProxy ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="rewardProxy"
              name="reward_proxy"
              stroke="#ff8f3d"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}
          {showPredictedOverlay && mergedVisibility.rewardProxy && hasPredictedRewardProxy ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="predictedRewardProxy"
              name="pred_reward_proxy"
              stroke="#ffd08a"
              strokeDasharray="6 3"
              strokeWidth={1.9}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.valenceProxy ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="valenceProxy"
              name="valence_proxy"
              stroke="#b185ff"
              strokeWidth={1.9}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.arousalProxy ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="arousalProxy"
              name="arousal_proxy"
              stroke="#ff6ca2"
              strokeWidth={1.9}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.noveltyProxy ? (
            <Line
              yAxisId="engagement"
              type="monotone"
              dataKey="noveltyProxy"
              name="novelty_proxy"
              stroke="#ffb347"
              strokeWidth={1.9}
              dot={false}
              connectNulls
            />
          ) : null}
          {mergedVisibility.trackingConfidence ? (
            <Line
              yAxisId="signals"
              type="monotone"
              dataKey="trackingConfidence"
              name="tracking_confidence"
              stroke="#90a6c8"
              strokeDasharray="4 2"
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ) : null}

          {selectedAuNames.map((auName, index) => (
            <Line
              key={`au-line-${auName}`}
              yAxisId="signals"
              type="monotone"
              dataKey={`au_${auName}`}
              name={auName}
              stroke={['#8f7aff', '#ff9b54', '#43d5c8', '#f5c86d', '#7ea4ff', '#ff7b90'][index % 6]}
              strokeWidth={1.75}
              dot={false}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
