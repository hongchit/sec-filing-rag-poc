import { Box, Chip, Stack, Typography } from '@mui/material';

const stages = [
  ['ask', 'Ask'],
  ['evidence', 'Retrieve filing evidence'],
  ['draft', 'Generate grounded answer'],
  ['cite', 'Attach citations'],
] as const;

export function EvaluationPipeline({ active = 'all' }: { active?: string }) {
  return (
    <Box component="section" aria-label="Grounded answer pipeline">
      <Typography variant="overline" color="primary">
        How Query answers a question
      </Typography>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        gap={0.75}
        flexWrap={{ sm: 'wrap' }}
        alignItems={{ xs: 'stretch', sm: 'center' }}
      >
        {stages.map(([id, label], index) => (
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            gap={0.75}
            alignItems={{ xs: 'stretch', sm: 'center' }}
            key={id}
          >
            {index > 0 && (
              <Typography
                aria-hidden="true"
                color="text.secondary"
                textAlign="center"
                lineHeight={1}
              >
                <Box component="span" sx={{ display: { xs: 'inline', sm: 'none' } }}>
                  ↓
                </Box>
                <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>
                  →
                </Box>
              </Typography>
            )}
            <Chip
              label={label}
              color={active === 'all' || active === id ? 'primary' : 'default'}
              variant={active === 'all' || active === id ? 'filled' : 'outlined'}
              sx={{ width: { xs: '100%', sm: 'auto' } }}
            />
          </Stack>
        ))}
      </Stack>
      <Typography color="text.secondary" mt={1}>
        Retrieval provides relevant filing passages for the answer model. Citations allow
        verification of results against sources. The evaluation pages separately assess evidence
        search and answer quality; the LLM-as-judge is used during testing, not in the actual Query
        flow.
      </Typography>
    </Box>
  );
}
