import ArrowForward from '@mui/icons-material/ArrowForward';
import { Box, Button, Card, CardContent, Grid, Stack, Typography } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { PublicOrAppLayout } from '../components/PublicOrAppLayout';

const benefits = [
  [
    'Use current documents',
    'Bring filing text into the answer at question time instead of relying only on model training memory.',
  ],
  ['Make answers reviewable', 'Citation handles point back to the passages supplied to the model.'],
  [
    'Measure quality',
    'Evaluate retrieval and generated answers separately before choosing production settings.',
  ],
];

export function Overview() {
  return (
    <PublicOrAppLayout>
      <Stack spacing={6}>
        <Box maxWidth={850}>
          <Typography variant="overline" color="primary">
            Why RAG
          </Typography>
          <Typography variant="h1">
            Give a language model the evidence it needs, when it needs it.
          </Typography>
          <Typography variant="h6" color="text.secondary" fontWeight={400} mt={2}>
            Retrieval-augmented generation, or RAG, searches approved documents for relevant
            passages and supplies them with the question. It helps answers use current source
            material without retraining the model.
          </Typography>
        </Box>
        <Box component="section" id="benefits">
          <Typography variant="overline" color="primary">
            Business value
          </Typography>
          <Typography variant="h2">Why add retrieval?</Typography>
          <Grid container spacing={2} mt={1}>
            {benefits.map(([title, body]) => (
              <Grid size={{ xs: 12, md: 4 }} key={title}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h3">{title}</Typography>
                    <Typography color="text.secondary" mt={1}>
                      {body}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
        <Box component="section" id="what-is-rag">
          <Typography variant="overline" color="primary">
            The idea
          </Typography>
          <Typography variant="h2">LLM alone vs RAG</Typography>
          <Grid container spacing={2} mt={1} aria-label="LLM alone and RAG comparison">
            {[
              [
                'LLM alone',
                [
                  'Relies on training memory',
                  'May be stale or unsupported',
                  'Does not cite the source document',
                ],
              ],
              [
                'With RAG',
                [
                  'Retrieves current documents',
                  'Adds grounded context',
                  'Produces a cited answer',
                  'Updates evidence without retraining',
                ],
              ],
            ].map(([title, points]) => (
              <Grid size={{ xs: 12, md: 6 }} key={title as string}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h3">{title as string}</Typography>
                    <Box component="ul" sx={{ pl: 3, mb: 0 }}>
                      {(points as string[]).map((point) => (
                        <Typography component="li" key={point}>
                          {point}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
        <Box component="section" id="sec-research">
          <Typography variant="overline" color="primary">
            RAG in action
          </Typography>
          <Typography variant="h2">Query public Form 10-K filings.</Typography>
          <Typography mt={1}>
            A Form 10-K is a company’s annual SEC filing. This platform searches selected sections
            covering the business, risks, legal proceedings, management analysis, market risk, and
            financial statements. Query supports nine configured companies; the current benchmark
            measures 96 questions across AAPL, MSFT, and NVDA only.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} gap={1.5} mt={2}>
            <Button
              variant="contained"
              component={RouterLink}
              to="/research"
              endIcon={<ArrowForward />}
            >
              Open Query
            </Button>
            <Button component={RouterLink} to="/how-it-works">
              See how it is built
            </Button>
            <Button component={RouterLink} to="/evaluation">
              See the evaluation
            </Button>
          </Stack>
        </Box>
      </Stack>
    </PublicOrAppLayout>
  );
}
