/**
 * Constants, config objects, types, and small presentational components
 * used by VideoDashboardPage.
 */

import { type ReactNode } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Typography
} from '@mui/material';
import { TermTooltip } from '../components/TermTooltip';
import type {
  AnnotationOverlayMarker,
  TelemetryOverlayMarker,
  ReadoutDiagnosticCard,
  ReadoutSegment,
  TraceLayerVisibility
} from '../types';

// ── Marker / telemetry labels ───────────────────────────────────────

export const MARKER_DISPLAY_LABEL: Record<AnnotationOverlayMarker['marker_type'], string> = {
  engaging_moment: 'Engaging',
  confusing_moment: 'Confusing',
  stop_watching_moment: 'Stop-watching',
  cta_landed_moment: 'CTA-landed'
};

export const TELEMETRY_KIND_LABEL: Record<TelemetryOverlayMarker['kind'], string> = {
  pause: 'Pause',
  seek: 'Seek',
  abandonment: 'Abandonment'
};

// ── Reliability ─────────────────────────────────────────────────────

export type ReliabilityComponentKey =
  | 'availability_score'
  | 'range_validity_score'
  | 'pathway_quality_score'
  | 'signal_health_score'
  | 'duration_accuracy_score'
  | 'rollup_integrity_score';

export const RELIABILITY_COMPONENTS: Array<{
  key: ReliabilityComponentKey;
  label: string;
  weight: number;
}> = [
  { key: 'availability_score', label: 'Availability', weight: 30 },
  { key: 'range_validity_score', label: 'Range Validity', weight: 20 },
  { key: 'pathway_quality_score', label: 'Pathway Quality', weight: 20 },
  { key: 'signal_health_score', label: 'Signal Health', weight: 15 },
  { key: 'duration_accuracy_score', label: 'Duration Accuracy', weight: 10 },
  { key: 'rollup_integrity_score', label: 'Rollup Integrity', weight: 5 }
];

// ── Trace legend ────────────────────────────────────────────────────

export const TRACE_LEGEND_ITEMS: Array<{
  label: string;
  color: string;
  description: string;
  dashed?: boolean;
}> = [
  {
    label: 'Attention Score',
    color: '#2f7dff',
    description: 'Blink-dynamics and passive playback continuity proxy (0-100, left axis).'
  },
  {
    label: 'Attention Velocity',
    color: '#8da2ff',
    description: 'Rate of change in attention (right axis).'
  },
  { label: 'Blink Rate', color: '#ff4d6d', description: 'Rolling blink frequency.' },
  {
    label: 'Blink Inhibition',
    color: '#58d4c1',
    description: 'Blink suppression relative to baseline.'
  },
  {
    label: 'Reward Proxy',
    color: '#ff8f3d',
    description: 'Facial-coding-derived reward proxy from AU signals (0-100, left axis).'
  },
  {
    label: 'Predicted Attention',
    color: '#7db3ff',
    description: 'Model prediction overlaid for comparison with measured behavior.',
    dashed: true
  },
  {
    label: 'Predicted Blink Inhibition',
    color: '#9af2e5',
    description: 'Model-predicted blink inhibition trend.',
    dashed: true
  },
  {
    label: 'Predicted Reward Proxy',
    color: '#ffd08a',
    description: 'Model-predicted reward proxy trend.',
    dashed: true
  },
  {
    label: 'Tracking Confidence',
    color: '#90a6c8',
    description: 'Quality/confidence estimate for webcam-derived traces.',
    dashed: true
  }
];

export const OVERLAY_LEGEND_ITEMS: Array<{
  label: string;
  color: string;
  description: string;
  dashed?: boolean;
}> = [
  {
    label: 'Scene bands',
    color: '#4a5a6e',
    description: 'Alternating background bands/scene boundary lines.'
  },
  { label: 'Cut markers', color: '#2c3a4c', description: 'Vertical cut boundaries.', dashed: true },
  {
    label: 'CTA markers',
    color: '#ffb347',
    description: 'Call-to-action timing windows.',
    dashed: true
  },
  {
    label: 'Annotation markers',
    color: '#7c3aed',
    description: 'Post-view engaging/confusing/stop/CTA labels.',
    dashed: true
  },
  {
    label: 'Telemetry markers',
    color: '#0ea5e9',
    description: 'Pause/seek/abandonment playback events.',
    dashed: true
  },
  {
    label: 'Low-confidence windows',
    color: '#fda4af',
    description: 'Shaded windows where webcam quality is weak.'
  }
];

// ── Abandonment / telemetry helpers ─────────────────────────────────

export const ABANDONMENT_EVENT_TYPES = new Set([
  'abandonment',
  'session_incomplete',
  'incomplete_session',
  'abandon'
]);

export const toTelemetryOverlayKind = (
  eventType: string
): TelemetryOverlayMarker['kind'] | null => {
  const normalized = eventType.trim().toLowerCase();
  if (normalized === 'pause') {
    return 'pause';
  }
  if (
    normalized === 'seek' ||
    normalized === 'seek_start' ||
    normalized === 'seek_end' ||
    normalized === 'rewind'
  ) {
    return 'seek';
  }
  if (ABANDONMENT_EVENT_TYPES.has(normalized)) {
    return 'abandonment';
  }
  return null;
};

// ── Trace layers ────────────────────────────────────────────────────

export const DEFAULT_TRACE_LAYER_VISIBILITY: TraceLayerVisibility = {
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

export const TRACE_LAYER_OPTIONS: Array<{
  key: keyof TraceLayerVisibility;
  label: string;
  testId: string;
  definitionKey: string;
}> = [
  {
    key: 'attentionScore',
    label: 'Attention Score',
    testId: 'toggle-attention-score',
    definitionKey: 'attention_score'
  },
  {
    key: 'attentionVelocity',
    label: 'Attention Velocity',
    testId: 'toggle-attention-velocity',
    definitionKey: 'attention_velocity'
  },
  {
    key: 'blinkRate',
    label: 'Blink Rate',
    testId: 'toggle-blink-rate',
    definitionKey: 'blink_rate'
  },
  {
    key: 'blinkInhibition',
    label: 'Blink Inhibition',
    testId: 'toggle-blink-inhibition',
    definitionKey: 'blink_inhibition'
  },
  {
    key: 'rewardProxy',
    label: 'Reward Proxy',
    testId: 'toggle-reward-proxy',
    definitionKey: 'reward_proxy'
  },
  {
    key: 'valenceProxy',
    label: 'Valence Proxy',
    testId: 'toggle-valence-proxy',
    definitionKey: 'valence_proxy'
  },
  {
    key: 'arousalProxy',
    label: 'Arousal Proxy',
    testId: 'toggle-arousal-proxy',
    definitionKey: 'arousal_proxy'
  },
  {
    key: 'noveltyProxy',
    label: 'Novelty Proxy',
    testId: 'toggle-novelty-proxy',
    definitionKey: 'novelty_proxy'
  },
  {
    key: 'trackingConfidence',
    label: 'Tracking Confidence',
    testId: 'toggle-tracking-confidence',
    definitionKey: 'tracking_confidence'
  }
];

// ── Accordion base style (Q8) ───────────────────────────────────────
export const ACCORDION_BASE_SX = {
  backgroundColor: 'transparent',
  boxShadow: 'none',
  '&::before': { display: 'none' },
} as const;

// ── Diagnostic cards ────────────────────────────────────────────────

export const DIAGNOSTIC_CARD_ORDER: ReadoutDiagnosticCard['card_type'][] = [
  'golden_scene',
  'hook_strength',
  'cta_receptivity',
  'attention_drop_scene',
  'confusion_scene',
  'recovery_scene'
];

export const DIAGNOSTIC_CARD_META: Record<
  ReadoutDiagnosticCard['card_type'],
  { title: string; subtitle: string }
> = {
  golden_scene: {
    title: 'Golden Scene',
    subtitle: 'Peak sustained reward/attention section.'
  },
  hook_strength: {
    title: 'Hook Strength',
    subtitle: 'Opening-window performance and retention.'
  },
  cta_receptivity: {
    title: 'CTA Receptivity',
    subtitle: 'Attention/reward around CTA lead-in and CTA window.'
  },
  attention_drop_scene: {
    title: 'Attention Drop Scene',
    subtitle: 'Largest sustained negative attention delta.'
  },
  confusion_scene: {
    title: 'Confusion Scene',
    subtitle: 'Friction indicators with falling attention.'
  },
  recovery_scene: {
    title: 'Recovery Scene',
    subtitle: 'Later segment where attention rebounds.'
  }
};

// ── Small presentational components ─────────────────────────────────

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
      <Typography
        variant="caption"
        sx={{
          fontFamily: '"JetBrains Mono", monospace',
          color: '#c8f031',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          flexShrink: 0,
          fontSize: '0.68rem'
        }}
      >
        {children}
      </Typography>
      <Box sx={{ flex: 1, height: '1px', background: '#26262f' }} />
    </Box>
  );
}

export type SegmentPanelProps = {
  title: string;
  subtitle: string;
  metricLabel: string;
  segments: ReadoutSegment[];
  onSeek: (seconds: number) => void;
  testId: string;
  definitionKey?: string;
};

export function SegmentPanel({
  title,
  subtitle,
  metricLabel,
  segments,
  onSeek,
  testId,
  definitionKey
}: SegmentPanelProps) {
  return (
    <Card data-testid={testId}>
      <CardContent>
        <Typography variant="h6" fontWeight={700} gutterBottom>
          {definitionKey ? <TermTooltip term={definitionKey}>{title}</TermTooltip> : title}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {subtitle}
        </Typography>
        <Divider sx={{ mb: 1.5 }} />
        {segments.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No segments detected.
          </Typography>
        ) : (
          <List dense>
            {segments.map((segment, index) => (
              <ListItem
                disablePadding
                key={`${title}-${segment.start_video_time_ms}-${segment.end_video_time_ms}-${index}`}
              >
                <ListItemButton
                  onClick={() => onSeek(segment.start_video_time_ms / 1000)}
                  data-testid={`segment-jump-${testId}-${index}`}
                >
                  <ListItemText
                    primary={`#${index + 1} ${(segment.start_video_time_ms / 1000).toFixed(1)}s - ${(segment.end_video_time_ms / 1000).toFixed(1)}s`}
                    secondary={[
                      `${metricLabel} ${segment.magnitude.toFixed(2)}`,
                      segment.confidence !== null && segment.confidence !== undefined
                        ? `confidence ${segment.confidence.toFixed(2)}`
                        : null,
                      segment.scene_id ? `scene ${segment.scene_id}` : null,
                      segment.cut_id ? `cut ${segment.cut_id}` : null,
                      segment.cta_id ? `cta ${segment.cta_id}` : null,
                      segment.reason_codes.length > 0 ? segment.reason_codes.join(', ') : null
                    ]
                      .filter(Boolean)
                      .join(' • ')}
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
