import {
  Alert,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography
} from '@mui/material';
import type { ProductRollupPresentation } from '../types';

type ProductRollupPanelProps = {
  productRollups?: ProductRollupPresentation | null;
};

function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? 'n/a' : value.toFixed(1);
}

function formatConfidence(value: number | null | undefined): string {
  return value === null || value === undefined ? 'n/a' : `${Math.round(value * 100)}%`;
}

export default function ProductRollupPanel({ productRollups }: ProductRollupPanelProps) {
  if (!productRollups) {
    return null;
  }

  const modeChipLabel =
    productRollups.mode === 'enterprise' ? 'Enterprise Mode' : 'Creator Mode';

  if (productRollups.mode === 'creator' && productRollups.creator) {
    const creator = productRollups.creator;
    return (
      <Card data-testid="product-rollup-creator-card">
        <CardContent>
          <Stack spacing={1.25}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="h6" fontWeight={700}>
                Creator Rollup Layer
              </Typography>
              <Chip label={modeChipLabel} color="primary" />
              <Chip label={`Tier ${productRollups.workspace_tier}`} variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Simplified product surface for creators. Underlying scores remain sourced from the shared taxonomy.
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip
                label={`${creator.reception_score.display_label} ${formatScore(
                  creator.reception_score.scalar_value
                )}`}
                color="primary"
                data-testid="creator-reception-score-chip"
              />
              <Chip
                label={`${creator.organic_reach_prior.display_label} ${formatScore(
                  creator.organic_reach_prior.scalar_value
                )}`}
                data-testid="creator-organic-reach-chip"
              />
              <Chip
                label={`Confidence ${formatConfidence(creator.reception_score.confidence)}`}
                data-testid="creator-reception-confidence-chip"
              />
            </Stack>
            {creator.explanations.map((line, index) => (
              <Typography key={`creator-explanation-${index}`} variant="body2" color="text.secondary">
                {line}
              </Typography>
            ))}
            {creator.warnings.length === 0 ? (
              <Alert severity="success" data-testid="creator-warning-empty">
                No high-priority creator warnings in this view.
              </Alert>
            ) : (
              <Stack spacing={0.75}>
                {creator.warnings.map((warning) => (
                  <Alert
                    key={warning.warning_key}
                    severity={warning.severity === 'high' ? 'warning' : 'info'}
                    data-testid={`creator-warning-${warning.warning_key}`}
                  >
                    <strong>{warning.warning_key}</strong>: {warning.message}
                  </Alert>
                ))}
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>
    );
  }

  if (productRollups.mode === 'enterprise' && productRollups.enterprise) {
    const enterprise = productRollups.enterprise;
    return (
      <Card data-testid="product-rollup-enterprise-card">
        <CardContent>
          <Stack spacing={1.25}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="h6" fontWeight={700}>
                Enterprise Rollup Layer
              </Typography>
              <Chip label={modeChipLabel} color="primary" />
              <Chip label={`Tier ${productRollups.workspace_tier}`} variant="outlined" />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Decision-support surface for media and creative teams. Predicted lift remains distinct from measured incrementality.
            </Typography>
            <Grid container spacing={1}>
              <Grid size={{ xs: 12, md: 4 }}>
                <Chip
                  label={`${enterprise.paid_lift_prior.display_label} ${formatScore(
                    enterprise.paid_lift_prior.scalar_value
                  )}`}
                  data-testid="enterprise-paid-lift-chip"
                />
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <Chip
                  label={`${enterprise.brand_memory_prior.display_label} ${formatScore(
                    enterprise.brand_memory_prior.scalar_value
                  )}`}
                  data-testid="enterprise-brand-memory-chip"
                />
              </Grid>
              <Grid size={{ xs: 12, md: 4 }}>
                <Chip
                  label={`${enterprise.cta_reception_score.display_label} ${formatScore(
                    enterprise.cta_reception_score.scalar_value
                  )}`}
                  data-testid="enterprise-cta-reception-chip"
                />
              </Grid>
            </Grid>
            <Alert severity="info" data-testid="enterprise-lift-distinction-note">
              Synthetic Lift Prior: {formatScore(enterprise.synthetic_lift_prior.scalar_value)} | Measured status:{' '}
              {enterprise.synthetic_vs_measured_lift.measured_lift_status}. {enterprise.synthetic_vs_measured_lift.note}
            </Alert>
            <Stack spacing={0.4}>
              <Typography variant="subtitle2" fontWeight={700}>
                Decision Support
              </Typography>
              <Typography variant="body2" color="text.secondary" data-testid="enterprise-media-summary">
                Media: {enterprise.decision_support.media_team_summary}
              </Typography>
              <Typography variant="body2" color="text.secondary" data-testid="enterprise-creative-summary">
                Creative: {enterprise.decision_support.creative_team_summary}
              </Typography>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
    );
  }

  return null;
}
