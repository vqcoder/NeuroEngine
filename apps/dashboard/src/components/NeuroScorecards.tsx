import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  Stack,
  Tooltip,
  Typography
} from '@mui/material';
import type {
  LegacyScoreAdapter,
  NeuroCompositeRollup,
  NeuroScoreContract,
  NeuroScoreTaxonomy
} from '../types';
import { TermTooltip } from './TermTooltip';

type NeuroScorecardsProps = {
  neuroScores?: NeuroScoreTaxonomy | null;
  legacyScoreAdapters?: LegacyScoreAdapter[];
  onSeek?: (seconds: number) => void;
};

const SCORE_ORDER: Array<keyof NeuroScoreTaxonomy['scores']> = [
  'arrest_score',
  'attentional_synchrony_index',
  'narrative_control_score',
  'blink_transport_score',
  'boundary_encoding_score',
  'reward_anticipation_index',
  'social_transmission_score',
  'self_relevance_score',
  'cta_reception_score',
  'synthetic_lift_prior',
  'au_friction_score'
];

const ROLLUP_ORDER: Array<keyof NeuroScoreTaxonomy['rollups']> = [
  'organic_reach_prior',
  'paid_lift_prior',
  'brand_memory_prior'
];

const STATUS_COLOR: Record<NeuroScoreContract['status'], 'success' | 'warning' | 'default'> = {
  available: 'success',
  insufficient_data: 'warning',
  unavailable: 'default'
};

const formatScore = (value: number | null): string => (value === null ? 'n/a' : value.toFixed(1));
const formatConfidence = (value: number | null): string =>
  value === null ? 'n/a' : `${(value * 100).toFixed(0)}%`;

function RollupCard({ rollup }: { rollup: NeuroCompositeRollup }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="subtitle1" fontWeight={700}>
              <TermTooltip term={rollup.machine_name}>{rollup.display_label}</TermTooltip>
            </Typography>
            <Chip size="small" label={rollup.machine_name} variant="outlined" />
            <Chip size="small" label={rollup.status} color={STATUS_COLOR[rollup.status]} />
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip size="small" label={`Score ${formatScore(rollup.scalar_value)}`} color="primary" />
            <Chip size="small" label={`Confidence ${formatConfidence(rollup.confidence)}`} />
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {rollup.claim_safe_description}
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}

function ScoreCard({
  score,
  onSeek
}: {
  score: NeuroScoreContract;
  onSeek?: (seconds: number) => void;
}) {
  return (
    <Card data-testid={`neuro-score-card-${score.machine_name}`}>
      <CardContent>
        <Stack spacing={1.1}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="h6" fontWeight={700}>
              <TermTooltip term={score.machine_name}>{score.display_label}</TermTooltip>
            </Typography>
            <Chip size="small" label={score.machine_name} variant="outlined" />
            <Chip size="small" label={score.status} color={STATUS_COLOR[score.status]} />
          </Stack>

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Chip label={`Score ${formatScore(score.scalar_value)}`} color="primary" data-testid={`score-${score.machine_name}`} />
            <Chip label={`Confidence ${formatConfidence(score.confidence)}`} />
            <Chip label={`Model ${score.model_version}`} variant="outlined" />
          </Stack>

          <Typography variant="body2" color="text.secondary">
            {score.claim_safe_description}
          </Typography>

          <Divider />

          <Typography variant="subtitle2" fontWeight={700}>
            Evidence windows
          </Typography>
          {score.evidence_windows.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No evidence windows in current selection.
            </Typography>
          ) : (
            <Stack spacing={0.6}>
              {score.evidence_windows.slice(0, 3).map((window, index) => (
                <Stack
                  key={`${score.machine_name}-window-${index}`}
                  direction={{ xs: 'column', sm: 'row' }}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                  spacing={0.5}
                >
                  <Typography variant="body2" color="text.secondary">
                    {(window.start_ms / 1000).toFixed(1)}s - {(window.end_ms / 1000).toFixed(1)}s • {window.reason}
                  </Typography>
                  {onSeek ? (
                    <Button
                      variant="text"
                      size="small"
                      onClick={() => onSeek(window.start_ms / 1000)}
                      data-testid={`neuro-score-jump-${score.machine_name}-${index}`}
                    >
                      Seek
                    </Button>
                  ) : null}
                </Stack>
              ))}
            </Stack>
          )}

          <Typography variant="subtitle2" fontWeight={700}>
            Top features
          </Typography>
          {score.top_feature_contributions.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No feature attributions available.
            </Typography>
          ) : (
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {score.top_feature_contributions.slice(0, 4).map((feature, index) => (
                <Tooltip
                  key={`${score.machine_name}-feature-${index}`}
                  title={feature.rationale ?? feature.feature_name}
                >
                  <Chip
                    size="small"
                    label={`${feature.feature_name} ${feature.contribution.toFixed(2)}`}
                    variant="outlined"
                  />
                </Tooltip>
              ))}
            </Stack>
          )}

          <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
            Provenance: {score.provenance}
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function NeuroScorecards({
  neuroScores,
  legacyScoreAdapters = [],
  onSeek
}: NeuroScorecardsProps) {
  if (!neuroScores) {
    return (
      <Card data-testid="neuro-scorecards-empty">
        <CardContent>
          <Alert severity="info">
            Neuro-score taxonomy is not available for this readout yet.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Stack spacing={2}>
      <Card data-testid="neuro-rollups-card">
        <CardContent>
          <Stack spacing={1.25}>
            <Typography variant="h6" fontWeight={700}>
              Neuro Composite Priors
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Composite priors summarize directional potential from diagnostic readout signals. These are probabilistic proxies, not causal incrementality proof.
            </Typography>
            <Grid container spacing={1.25}>
              {ROLLUP_ORDER.map((key) => (
                <Grid key={key} size={{ xs: 12, md: 4 }}>
                  <RollupCard rollup={neuroScores.rollups[key]} />
                </Grid>
              ))}
            </Grid>
            <Divider />
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {legacyScoreAdapters.map((adapter) => (
                <Chip
                  key={`legacy-${adapter.legacy_output}`}
                  size="small"
                  label={`Legacy ${adapter.legacy_output} -> ${adapter.mapped_machine_name} (${adapter.status})`}
                  variant="outlined"
                  data-testid={`legacy-adapter-${adapter.legacy_output}`}
                />
              ))}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Box>
        <Grid container spacing={2}>
          {SCORE_ORDER.map((key) => (
            <Grid key={key} size={{ xs: 12, md: 6, lg: 4 }}>
              <ScoreCard score={neuroScores.scores[key]} onSeek={onSeek} />
            </Grid>
          ))}
        </Grid>
      </Box>
    </Stack>
  );
}
