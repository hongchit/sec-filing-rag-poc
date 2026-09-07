import GitHub from '@mui/icons-material/GitHub';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Link,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { Figure } from '../components/Figure';
import { PublicOrAppLayout } from '../components/PublicOrAppLayout';
import { SectionNavigation } from '../components/SectionNavigation';

const improvements = [
  [
    'Query rewriting and multi-hop retrieval',
    'Break complex questions into focused searches and combine evidence gathered across several steps.',
    'Better coverage for paraphrased and multi-part questions.',
  ],
  [
    'Evidence reranking',
    'Use a small specialized model to compare the question with each candidate after fast retrieval.',
    'Only the strongest evidence reaches the answer model, reducing distraction and prompt size.',
  ],
  [
    'Cross-company and multi-year research',
    'Retrieve from several approved filings while preserving the source of every passage.',
    'Support comparisons and questions that span reporting periods.',
  ],
  [
    'Structured table understanding',
    'Reconstruct rows, columns, headings, and footnotes instead of relying only on flattened text.',
    'Improve answers based on dense financial disclosures.',
  ],
  [
    'Image and chart understanding',
    'Use OCR or vision models to create source-linked descriptions and extracted facts.',
    'Make meaningful visual filing content searchable and citable.',
  ],
  [
    'Adaptive document preparation',
    'Choose chunk boundaries and retrieval depth based on document structure and question needs.',
    'Preserve context around long or unusually structured disclosures.',
  ],
  [
    'Bounded agentic retrieval',
    'Let the model request more evidence and select another Item, ticker, or filing within explicit step, cost, access, and safety limits.',
    'Gather enough evidence for harder questions without an uncontrolled research loop.',
  ],
  [
    'Knowledge graph retrieval',
    'Extract entities and relationships such as companies, products, risks, subsidiaries, and counterparties into a graph.',
    'Answer relational questions that are difficult to resolve from isolated passages.',
  ],
];
export function HowItWorks() {
  return (
    <PublicOrAppLayout>
      <Grid container spacing={4}>
        <Grid size={{ xs: 12, md: 3 }}>
          <SectionNavigation
            label="On this page"
            items={[
              { label: 'RAG pipeline', href: '#pipeline' },
              { label: 'Trusted data layers', href: '#data-layers' },
              { label: 'Building blocks', href: '#architecture' },
              { label: 'Evaluation', href: '#quality' },
              { label: 'Future improvements', href: '#improvements' },
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 9 }}>
          <Stack spacing={6}>
            <Box>
              <Typography variant="overline" color="primary">
                Inside the system
              </Typography>
              <Typography variant="h1">A basic RAG implementation, measured end to end.</Typography>
              <Typography variant="h6" color="text.secondary" fontWeight={400} mt={2}>
                This portfolio project applies RAG concepts learnt from{' '}
                <Link
                  href="https://github.com/DataTalksClub/llm-zoomcamp"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  DataTalkClub LLM Zoomcamp
                </Link>{' '}
                on{' '}
                <Link
                  href="https://www.sec.gov/submit-filings/about-edgar"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  public SEC filings
                </Link>
                : ingestion, hybrid retrieval, grounded generation, evaluation, monitoring, and cost
                tracking.
              </Typography>
              <Typography variant="h6" color="text.secondary" fontWeight={400} mt={2}>
                In data retrieval, the system uses a combination of keyword and semantic search to
                find relevant information in the filings. The system then passes the retrieved
                information to a large language model (LLM) to generate answers to user queries. The
                system also includes evaluation mechanisms to assess the quality of the retrieved
                information and generated answers, ensuring users receive accurate, reliable
                responses.
              </Typography>
            </Box>
            <Box component="section" id="pipeline">
              <Typography variant="h2">Two connected pipelines</Typography>
              <Figure
                src="/diagrams/rag-loop.svg"
                alt="A filing preparation pipeline feeds an index used by a question-time retrieval and answer pipeline."
                caption="The same prepared index supports many questions; the language model receives only the retrieved passages for the current request."
              />
              <Grid container spacing={2} mt={1}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Card>
                    <CardContent>
                      <Typography variant="h3">Filing ingestion</Typography>
                      <Typography mt={1}>
                        Acquire and checksum the original filing, sanitize and extract six Items,
                        create deterministic chunks and embeddings, persist bronze, silver, and gold
                        data, validate, then activate. Kestra sequences the batch work and manages
                        retries.
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Card>
                    <CardContent>
                      <Typography variant="h3">On each query request</Typography>
                      <Typography mt={1}>
                        Pin a corpus version, perform weighted hybrid retrieval, assemble the
                        prompt, generate structured paragraphs, validate policy and citations, and
                        then save evidence, usage, latency, and cost.
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Box>
            <Box component="section" id="data-layers">
              <Typography variant="overline" color="primary">
                Trusted by design
              </Typography>
              <Typography variant="h2">Three data layers, each with one clear job.</Typography>
              <Typography mt={1} color="text.secondary">
                The filing moves through bronze, silver, and gold layers so the original evidence
                stays traceable while the prepared content becomes reliable and fast to search.
              </Typography>
              <Figure
                src="/diagrams/medallion-data-layers.svg"
                alt="Bronze preserves the original filing, silver organizes trusted versioned content, and gold makes it fast to search."
                caption="Each layer adds a focused capability without replacing the evidence held by the layer before it."
              />
              <Grid container spacing={2} mt={1}>
                {[
                  [
                    'Bronze — Preserve the source',
                    'Keeps the filing evidence received from the SEC so its origin and integrity can be verified later.',
                  ],
                  [
                    'Silver — Build trusted knowledge',
                    'Organizes filing sections into versioned, citation-ready passages so results remain reproducible.',
                  ],
                  [
                    'Gold — Search efficiently',
                    'Prepares those trusted passages for fast keyword and semantic search without becoming the source of truth.',
                  ],
                ].map(([title, body]) => (
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
              <Typography mt={2}>
                This separation connects every cited answer to a searchable passage, the prepared
                filing collection, and ultimately the original filing—while new filings and search
                improvements can be introduced safely.
              </Typography>
            </Box>
            <Box component="section" id="architecture">
              <Typography variant="h2">Building blocks</Typography>
              <Grid container spacing={2} mt={1}>
                {[
                  [
                    'Frontend: React + MUI',
                    'Responsive interface and accessible interaction patterns.',
                  ],
                  [
                    'Backend: FastAPI',
                    'Authentication, policy, budgets, retrieval, generation, and public APIs.',
                  ],
                  ['Database: PostgreSQL', 'Versioned filing layers plus BM25 and vector search.'],
                  ['Workflow Pipeline: Kestra', 'Batch ingestion orchestration.'],
                  ['Datasource: SEC EDGAR', 'Authoritative public filing source.'],
                  [
                    'LLM Processing: OpenAI API',
                    'Embeddings, grounded answer generation, and evaluation judging.',
                  ],
                ].map(([title, body]) => (
                  <Grid size={{ xs: 12, sm: 6 }} key={title}>
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
              <Alert severity="info" sx={{ mt: 2 }}>
                Application data remains under application control. Selected public filing passages
                are sent to model providers for embeddings or answers; credentials and private user
                data are not part of those prompts.
              </Alert>
            </Box>
            <Box component="section" id="quality">
              <Typography variant="h2">What makes a useful RAG system?</Typography>
              <Stack direction="row" gap={1} flexWrap="wrap" mt={2}>
                {[
                  'Clean chunks',
                  'Hybrid search',
                  'Retrieval evaluation',
                  'Grounded prompts',
                  'Citation validation',
                  'RAG evaluation',
                  'Usage and cost monitoring',
                ].map((label) => (
                  <Chip key={label} label={label} />
                ))}
              </Stack>
              <Typography mt={2}>
                Retrieval evaluation determines if the expected passage was retrieved and its
                ranking. RAG evaluation assesses whether the provided evidence yields a responsive,
                supported, and cited answer. The benchmark involves selecting a candidate, which a
                person then promotes for the Query.
              </Typography>
              <Button component={RouterLink} to="/evaluation" sx={{ mt: 1 }}>
                Explore the measured results
              </Button>
            </Box>
            <Box component="section" id="improvements">
              <Typography variant="overline" color="primary">
                Where this can go next
              </Typography>
              <Typography variant="h2">Future improvements for richer research</Typography>
              <Typography mt={1} color="text.secondary">
                The current system establishes a measured, traceable RAG foundation. These
                extensions can build on it incrementally while preserving source lineage and
                citation checks.
              </Typography>
              <Table sx={{ mt: 2 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Improvement</TableCell>
                    <TableCell>What it adds</TableCell>
                    <TableCell>Expected benefit</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {improvements.map((row) => (
                    <TableRow key={row[0]}>
                      {row.map((cell) => (
                        <TableCell key={cell}>{cell}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Typography mt={2}>
                These are future capabilities, not features of the current POC. Its layered
                architecture allows these to be added and tested without compromising the original
                evidence, stable citations, or visibility into quality, latency, and cost.
              </Typography>
            </Box>
            <Link
              href="https://github.com/hongchit/sec-filing-rag-poc"
              target="_blank"
              rel="noreferrer"
              display="inline-flex"
              gap={1}
              alignItems="center"
            >
              <GitHub /> View the project source codes on GitHub
            </Link>
          </Stack>
        </Grid>
      </Grid>
    </PublicOrAppLayout>
  );
}
