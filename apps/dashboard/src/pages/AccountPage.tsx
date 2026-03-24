import { Box, Button, Typography } from '@mui/material';
import type { WorkspaceTier } from '../hooks/useAuth';

const TIER_INFO: Record<WorkspaceTier, { label: string; color: string; description: string }> = {
  free: {
    label: 'Free',
    color: '#6b7280',
    description: 'Basic access — limited neuro scores',
  },
  creator: {
    label: 'Creator',
    color: '#22c55e',
    description: 'Creator plan — full neuro scorecard and readout',
  },
  enterprise: {
    label: 'Enterprise',
    color: '#f59e0b',
    description: 'Enterprise plan — full access including decision support',
  },
};

interface AccountPageProps {
  tier: WorkspaceTier;
  userEmail?: string;
  onSignOut?: () => void;
}

export default function AccountPage({ tier, userEmail, onSignOut }: AccountPageProps) {
  const info = TIER_INFO[tier];

  return (
    <Box sx={{ maxWidth: 480, mx: 'auto', mt: 6, px: 3 }}>
      <Typography
        sx={{
          fontFamily: '"DM Sans", sans-serif',
          fontWeight: 700,
          fontSize: '1.25rem',
          color: '#e8e6e3',
          mb: 3,
        }}
      >
        Account
      </Typography>

      <Box sx={{ mb: 3 }}>
        <Typography sx={{ color: '#8a8895', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.5 }}>
          Email
        </Typography>
        <Typography sx={{ color: '#e8e6e3', fontFamily: '"JetBrains Mono", monospace', fontSize: '0.85rem' }}>
          {userEmail ?? '—'}
        </Typography>
      </Box>

      <Box sx={{ mb: 3 }}>
        <Typography sx={{ color: '#8a8895', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.5 }}>
          Plan
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Box
            sx={{
              px: 0.75,
              py: 0.15,
              borderRadius: '4px',
              border: `1px solid ${info.color}40`,
              color: info.color,
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: '0.65rem',
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
            }}
          >
            {info.label}
          </Box>
        </Box>
        <Typography sx={{ color: '#8a8895', fontSize: '0.8rem', mt: 0.5 }}>
          {info.description}
        </Typography>
      </Box>

      <Typography sx={{ color: '#5a5866', fontSize: '0.72rem', mb: 3 }}>
        To change your plan, contact support.
      </Typography>

      {onSignOut && (
        <Button
          variant="outlined"
          size="small"
          onClick={onSignOut}
          sx={{
            color: '#8a8895',
            borderColor: '#26262f',
            textTransform: 'none',
            fontSize: '0.78rem',
            '&:hover': { borderColor: '#8a8895' },
          }}
        >
          Sign Out
        </Button>
      )}
    </Box>
  );
}
