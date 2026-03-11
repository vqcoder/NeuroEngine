import { type ReactNode } from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import { DEFINITIONS } from '../utils/definitions';

interface TermTooltipProps {
  term: string;
  children: ReactNode;
}

export function TermTooltip({ term, children }: TermTooltipProps) {
  const def = DEFINITIONS[term];
  if (!def) return <>{children}</>;

  const title = (
    <Box sx={{ p: 0.25 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mb: 0.5, color: '#c8f031' }}>
        {def.label}
      </Typography>
      <Typography variant="caption" sx={{ display: 'block', color: '#e8e6e3', lineHeight: 1.5 }}>
        {def.description}
      </Typography>
      {def.formula && (
        <Typography
          variant="caption"
          sx={{
            display: 'block',
            mt: 0.75,
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: '0.65rem',
            color: '#8a8895',
            borderTop: '1px solid #26262f',
            pt: 0.75
          }}
        >
          {def.formula}
        </Typography>
      )}
    </Box>
  );

  return (
    <Tooltip
      title={title}
      arrow
      placement="top"
      enterDelay={200}
      componentsProps={{
        tooltip: {
          sx: {
            bgcolor: '#141419',
            border: '1px solid #26262f',
            maxWidth: 300,
            '& .MuiTooltip-arrow': { color: '#141419' }
          }
        }
      }}
    >
      <Box
        component="span"
        sx={{
          borderBottom: '1px dashed rgba(200,240,49,0.4)',
          cursor: 'help',
          '&:hover': { borderBottomColor: '#c8f031' }
        }}
      >
        {children}
      </Box>
    </Tooltip>
  );
}
