/**
 * Section 4 — Signal Diagnostics (aggregate-only).
 * Extracted from VideoDashboardPage to reduce file size.
 */

import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography
} from '@mui/material';
import { TermTooltip } from '../components/TermTooltip';
import type { VideoReadout } from '../types';
import {
  formatConfidence,
  formatIndexScore,
  formatNarrativePathway,
  formatRewardAnticipationPathway,
  formatSynchrony,
  formatSynchronyPathway,
  isFiniteSynchrony,
  normalizeIndexToSignedSynchrony
} from '../utils/videoDashboard';
import { SectionLabel } from './videoDashboardConstants';

type SignalDiagnosticsSectionProps = {
  aggregateMetrics: NonNullable<VideoReadout['aggregate_metrics']>;
  onSeek: (seconds: number) => void;
};

export default function SignalDiagnosticsSection({
  aggregateMetrics,
  onSeek
}: SignalDiagnosticsSectionProps) {
  const attentionalSynchronyDiagnostics = aggregateMetrics.attentional_synchrony ?? null;
  const narrativeControlDiagnostics = aggregateMetrics.narrative_control ?? null;
  const rewardAnticipationDiagnostics = aggregateMetrics.reward_anticipation ?? null;

  const resolvedAttentionSynchrony =
    aggregateMetrics.attention_synchrony ??
    normalizeIndexToSignedSynchrony(attentionalSynchronyDiagnostics?.global_score);

  const resolvedGripControlScore = (() => {
    if (
      aggregateMetrics.grip_control_score !== null &&
      aggregateMetrics.grip_control_score !== undefined
    ) {
      return aggregateMetrics.grip_control_score;
    }
    const fallbackComponents = [
      resolvedAttentionSynchrony,
      aggregateMetrics.blink_synchrony
    ].filter(isFiniteSynchrony);
    if (fallbackComponents.length > 0) {
      return fallbackComponents.reduce((sum, value) => sum + value, 0) / fallbackComponents.length;
    }
    return normalizeIndexToSignedSynchrony(narrativeControlDiagnostics?.global_score);
  })();

  return (
    <Box>
      <SectionLabel>04 — Signal Diagnostics</SectionLabel>
      <Stack spacing={2}>
        {/* Grip / Control Score */}
        <Card data-testid="grip-control-card">
          <CardContent>
            <Typography variant="h6" fontWeight={700} gutterBottom>
              <TermTooltip term="grip_control_score">Grip / Control Score</TermTooltip>
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Panel synchrony across sessions after quality/confidence weighting.
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              <Chip
                label={`Attention synchrony ${formatSynchrony(resolvedAttentionSynchrony)}`}
                data-testid="attention-synchrony-chip"
              />
              <Chip
                label={`Blink synchrony ${formatSynchrony(aggregateMetrics.blink_synchrony)}`}
                data-testid="blink-synchrony-chip"
              />
              <Chip
                label={`Grip score ${formatSynchrony(resolvedGripControlScore)}`}
                color="primary"
                data-testid="grip-score-chip"
              />
            </Stack>
            <Typography variant="body2" color="text.secondary" mt={1.25}>
              Included sessions {aggregateMetrics.included_sessions ?? 0}
              {' • '}Downweighted {aggregateMetrics.downweighted_sessions ?? 0}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              CI method: {aggregateMetrics.ci_method ?? 'n/a'}
            </Typography>
          </CardContent>
        </Card>

        {/* Attentional Synchrony Index */}
        <Card data-testid="attentional-synchrony-card">
          <CardContent>
            <Typography variant="h6" fontWeight={700} gutterBottom>
              <TermTooltip term="attentional_synchrony_index">
                Attentional Synchrony Index
              </TermTooltip>
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Convergence proxy for shared viewer focus timing. Direct panel gaze preferred; fallback
              proxy carries lower confidence.
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              <Chip
                label={`Pathway ${formatSynchronyPathway(attentionalSynchronyDiagnostics?.pathway)}`}
                color={
                  attentionalSynchronyDiagnostics?.pathway === 'direct_panel_gaze'
                    ? 'success'
                    : attentionalSynchronyDiagnostics?.pathway === 'fallback_proxy'
                      ? 'warning'
                      : 'default'
                }
                data-testid="attentional-synchrony-pathway-chip"
              />
              <Chip
                label={`Global ${formatIndexScore(attentionalSynchronyDiagnostics?.global_score)}`}
                color="primary"
                data-testid="attentional-synchrony-global-chip"
              />
              <Chip
                label={`Confidence ${formatConfidence(attentionalSynchronyDiagnostics?.confidence)}`}
                data-testid="attentional-synchrony-confidence-chip"
              />
            </Stack>
            <Typography
              variant="body2"
              color="text.secondary"
              mt={1.25}
              data-testid="attentional-synchrony-evidence-summary"
            >
              {attentionalSynchronyDiagnostics?.evidence_summary ??
                'No attentional synchrony diagnostics returned for this aggregate view.'}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
              Signals:{' '}
              {attentionalSynchronyDiagnostics?.signals_used?.length
                ? attentionalSynchronyDiagnostics.signals_used.join(', ')
                : 'n/a'}
            </Typography>
            <Grid container spacing={1.25} mt={0.5}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Timeline Segments
                </Typography>
                {(attentionalSynchronyDiagnostics?.segment_scores ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No timeline segment diagnostics.
                  </Typography>
                ) : (
                  <List dense>
                    {(attentionalSynchronyDiagnostics?.segment_scores ?? [])
                      .slice(0, 3)
                      .map((segment, index) => (
                        <ListItem
                          key={`synchrony-segment-${segment.start_ms}-${segment.end_ms}-${index}`}
                          secondaryAction={
                            <Button
                              size="small"
                              onClick={() => onSeek(segment.start_ms / 1000)}
                              data-testid={`attentional-synchrony-segment-jump-${index}`}
                            >
                              Jump
                            </Button>
                          }
                        >
                          <ListItemText
                            primary={`${(segment.start_ms / 1000).toFixed(1)}s–${(segment.end_ms / 1000).toFixed(1)}s • ${formatIndexScore(segment.score)} / ${formatConfidence(segment.confidence)}`}
                            secondary={segment.reason}
                          />
                        </ListItem>
                      ))}
                  </List>
                )}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Peaks / Valleys
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1} mt={0.75}>
                  {(attentionalSynchronyDiagnostics?.peaks ?? [])
                    .slice(0, 2)
                    .map((peak, index) => (
                      <Chip
                        key={`synchrony-peak-${peak.start_ms}-${peak.end_ms}-${index}`}
                        color="success"
                        label={`Peak ${(peak.start_ms / 1000).toFixed(1)}s ${formatIndexScore(peak.score)}`}
                        data-testid={`attentional-synchrony-peak-chip-${index}`}
                      />
                    ))}
                  {(attentionalSynchronyDiagnostics?.valleys ?? [])
                    .slice(0, 2)
                    .map((valley, index) => (
                      <Chip
                        key={`synchrony-valley-${valley.start_ms}-${valley.end_ms}-${index}`}
                        color="warning"
                        label={`Valley ${(valley.start_ms / 1000).toFixed(1)}s ${formatIndexScore(valley.score)}`}
                        data-testid={`attentional-synchrony-valley-chip-${index}`}
                      />
                    ))}
                </Stack>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Narrative Control Score */}
        <Card data-testid="narrative-control-card">
          <CardContent>
            <Typography variant="h6" fontWeight={700} gutterBottom>
              <TermTooltip term="narrative_control_score">Narrative Control Score</TermTooltip>
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Proxy for how consistently cinematic grammar and transition structure guide viewer
              understanding over time.
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              <Chip
                label={`Pathway ${formatNarrativePathway(narrativeControlDiagnostics?.pathway)}`}
                color={
                  narrativeControlDiagnostics?.pathway === 'timeline_grammar'
                    ? 'success'
                    : narrativeControlDiagnostics?.pathway === 'fallback_proxy'
                      ? 'warning'
                      : 'default'
                }
                data-testid="narrative-control-pathway-chip"
              />
              <Chip
                label={`Global ${formatIndexScore(narrativeControlDiagnostics?.global_score)}`}
                color="primary"
                data-testid="narrative-control-global-chip"
              />
              <Chip
                label={`Confidence ${formatConfidence(narrativeControlDiagnostics?.confidence)}`}
                data-testid="narrative-control-confidence-chip"
              />
              <Chip
                label={`Heuristics ${(narrativeControlDiagnostics?.heuristic_checks ?? []).filter((item) => item.passed).length}/${(narrativeControlDiagnostics?.heuristic_checks ?? []).length}`}
                data-testid="narrative-control-heuristics-chip"
              />
            </Stack>
            <Typography
              variant="body2"
              color="text.secondary"
              mt={1.25}
              data-testid="narrative-control-evidence-summary"
            >
              {narrativeControlDiagnostics?.evidence_summary ??
                'No narrative control diagnostics returned for this aggregate view.'}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
              Signals:{' '}
              {narrativeControlDiagnostics?.signals_used?.length
                ? narrativeControlDiagnostics.signals_used.join(', ')
                : 'n/a'}
            </Typography>
            <Grid container spacing={1.25} mt={0.5}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Per-scene control
                </Typography>
                {(narrativeControlDiagnostics?.scene_scores ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No per-scene narrative diagnostics.
                  </Typography>
                ) : (
                  <List dense>
                    {(narrativeControlDiagnostics?.scene_scores ?? [])
                      .slice(0, 4)
                      .map((scene, index) => (
                        <ListItem
                          key={`narrative-scene-${scene.start_ms}-${scene.end_ms}-${index}`}
                          secondaryAction={
                            <Button
                              size="small"
                              onClick={() => onSeek(scene.start_ms / 1000)}
                              data-testid={`narrative-control-scene-jump-${index}`}
                            >
                              Jump
                            </Button>
                          }
                        >
                          <ListItemText
                            primary={`${(scene.start_ms / 1000).toFixed(1)}s–${(scene.end_ms / 1000).toFixed(1)}s • ${formatIndexScore(scene.score)} / ${formatConfidence(scene.confidence)}`}
                            secondary={[
                              scene.scene_label ?? scene.scene_id ?? null,
                              scene.summary,
                              scene.fragmentation_index !== null &&
                              scene.fragmentation_index !== undefined
                                ? `fragmentation ${scene.fragmentation_index.toFixed(2)}`
                                : null,
                              scene.boundary_density !== null &&
                              scene.boundary_density !== undefined
                                ? `boundaries ${scene.boundary_density.toFixed(2)}`
                                : null
                            ]
                              .filter(Boolean)
                              .join(' • ')}
                          />
                        </ListItem>
                      ))}
                  </List>
                )}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Top moments / heuristic checks
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1} mt={0.75}>
                  {(narrativeControlDiagnostics?.top_contributing_moments ?? [])
                    .slice(0, 3)
                    .map((moment, index) => (
                      <Chip
                        key={`narrative-moment-${moment.start_ms}-${moment.end_ms}-${index}`}
                        color={moment.contribution >= 0 ? 'success' : 'warning'}
                        label={`${moment.category} ${moment.contribution >= 0 ? '+' : ''}${moment.contribution.toFixed(1)}`}
                        data-testid={`narrative-control-moment-chip-${index}`}
                      />
                    ))}
                </Stack>
                {(narrativeControlDiagnostics?.heuristic_checks ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary" mt={1}>
                    No heuristic checks available.
                  </Typography>
                ) : (
                  <List dense>
                    {(narrativeControlDiagnostics?.heuristic_checks ?? [])
                      .slice(0, 4)
                      .map((heuristic, index) => (
                        <ListItem
                          key={`narrative-heuristic-${heuristic.heuristic_key}-${index}`}
                        >
                          <ListItemText
                            primary={`${heuristic.passed ? 'Pass' : 'Check'} • ${heuristic.heuristic_key}`}
                            secondary={`${heuristic.reason} (${heuristic.score_delta >= 0 ? '+' : ''}${heuristic.score_delta.toFixed(1)})`}
                          />
                        </ListItem>
                      ))}
                  </List>
                )}
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Reward Anticipation Index */}
        <Card data-testid="reward-anticipation-card">
          <CardContent>
            <Typography variant="h6" fontWeight={700} gutterBottom>
              <TermTooltip term="reward_anticipation_index">
                Reward Anticipation Index
              </TermTooltip>
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Claim-safe proxy for anticipatory pull into payoff moments based on pacing, blink
              suppression, and attention concentration dynamics.
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1}>
              <Chip
                label={`Pathway ${formatRewardAnticipationPathway(rewardAnticipationDiagnostics?.pathway)}`}
                color={
                  rewardAnticipationDiagnostics?.pathway === 'timeline_dynamics'
                    ? 'success'
                    : rewardAnticipationDiagnostics?.pathway === 'fallback_proxy'
                      ? 'warning'
                      : 'default'
                }
                data-testid="reward-anticipation-pathway-chip"
              />
              <Chip
                label={`Global ${formatIndexScore(rewardAnticipationDiagnostics?.global_score)}`}
                color="primary"
                data-testid="reward-anticipation-global-chip"
              />
              <Chip
                label={`Confidence ${formatConfidence(rewardAnticipationDiagnostics?.confidence)}`}
                data-testid="reward-anticipation-confidence-chip"
              />
              <Chip
                label={`Warnings ${(rewardAnticipationDiagnostics?.warnings ?? []).length}`}
                color={
                  (rewardAnticipationDiagnostics?.warnings ?? []).length > 0 ? 'warning' : 'default'
                }
                data-testid="reward-anticipation-warnings-chip"
              />
            </Stack>
            <Typography
              variant="body2"
              color="text.secondary"
              mt={1.25}
              data-testid="reward-anticipation-evidence-summary"
            >
              {rewardAnticipationDiagnostics?.evidence_summary ??
                'No reward anticipation diagnostics returned for this aggregate view.'}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
              Signals:{' '}
              {rewardAnticipationDiagnostics?.signals_used?.length
                ? rewardAnticipationDiagnostics.signals_used.join(', ')
                : 'n/a'}
            </Typography>
            <Grid container spacing={1.25} mt={0.5}>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Anticipation ramps
                </Typography>
                {(rewardAnticipationDiagnostics?.anticipation_ramps ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No anticipation ramps detected.
                  </Typography>
                ) : (
                  <List dense>
                    {(rewardAnticipationDiagnostics?.anticipation_ramps ?? [])
                      .slice(0, 4)
                      .map((ramp, index) => (
                        <ListItem
                          key={`reward-ramp-${ramp.start_ms}-${ramp.end_ms}-${index}`}
                          secondaryAction={
                            <Button
                              size="small"
                              onClick={() => onSeek(ramp.start_ms / 1000)}
                              data-testid={`reward-anticipation-ramp-jump-${index}`}
                            >
                              Jump
                            </Button>
                          }
                        >
                          <ListItemText
                            primary={`${(ramp.start_ms / 1000).toFixed(1)}s–${(ramp.end_ms / 1000).toFixed(1)}s • ${formatIndexScore(ramp.score)} / ${formatConfidence(ramp.confidence)}`}
                            secondary={[
                              ramp.reason,
                              ramp.ramp_slope !== null && ramp.ramp_slope !== undefined
                                ? `slope ${ramp.ramp_slope.toFixed(2)}`
                                : null,
                              ramp.tension_level !== null && ramp.tension_level !== undefined
                                ? `tension ${ramp.tension_level.toFixed(2)}`
                                : null
                            ]
                              .filter(Boolean)
                              .join(' • ')}
                          />
                        </ListItem>
                      ))}
                  </List>
                )}
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Payoff windows / warnings
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1} mt={0.75}>
                  {(rewardAnticipationDiagnostics?.payoff_windows ?? [])
                    .slice(0, 3)
                    .map((window, index) => (
                      <Chip
                        key={`reward-payoff-${window.start_ms}-${window.end_ms}-${index}`}
                        color={window.score >= 60 ? 'success' : 'warning'}
                        label={`${(window.start_ms / 1000).toFixed(1)}s ${formatIndexScore(window.score)}`}
                        data-testid={`reward-anticipation-payoff-chip-${index}`}
                      />
                    ))}
                </Stack>
                {(rewardAnticipationDiagnostics?.warnings ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary" mt={1}>
                    No tension-resolution warnings.
                  </Typography>
                ) : (
                  <List dense>
                    {(rewardAnticipationDiagnostics?.warnings ?? [])
                      .slice(0, 4)
                      .map((warning, index) => (
                        <ListItem key={`reward-warning-${warning.warning_key}-${index}`}>
                          <ListItemText
                            primary={`${warning.severity.toUpperCase()} • ${warning.warning_key}`}
                            secondary={[
                              warning.message,
                              warning.start_ms !== null && warning.start_ms !== undefined
                                ? `start ${(warning.start_ms / 1000).toFixed(1)}s`
                                : null,
                              warning.end_ms !== null && warning.end_ms !== undefined
                                ? `end ${(warning.end_ms / 1000).toFixed(1)}s`
                                : null,
                              warning.metric_value !== null && warning.metric_value !== undefined
                                ? `value ${warning.metric_value.toFixed(2)}`
                                : null
                            ]
                              .filter(Boolean)
                              .join(' • ')}
                          />
                        </ListItem>
                      ))}
                  </List>
                )}
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Stack>
    </Box>
  );
}
