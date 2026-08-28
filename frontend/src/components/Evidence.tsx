import CloseIcon from '@mui/icons-material/Close';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import OpenInNewIcon from '@mui/icons-material/OpenInNewOutlined';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  Link,
  Stack,
  Typography,
} from '@mui/material';
import { useEffect, useRef, useState } from 'react';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { getJson } from '../api';
import type { Chunk, EvaluationCase, FullChunk } from '../types';
function ExpectedCard({
  chunk,
  onExpand,
  selected,
}: {
  chunk: Chunk;
  onExpand: (id: string) => void;
  selected: boolean;
}) {
  const location = useLocation();
  const citation = chunk.citation || chunk.chunk_id;
  return (
    <Card
      component="article"
      sx={{
        flexShrink: 0,
        borderColor: selected ? 'primary.main' : 'divider',
        bgcolor: selected ? 'primary.light' : 'background.paper',
      }}
    >
      <CardContent sx={{ pb: 1 }}>
        <Typography fontWeight={700}>Expected evidence</Typography>
        <Typography component="code" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
          {citation}
        </Typography>
        <Typography sx={{ mt: 1 }}>{chunk.preview}</Typography>
        <Typography variant="caption" color="text.secondary">
          {chunk.ticker} · Item {chunk.item} · {chunk.accession}
        </Typography>
      </CardContent>
      <CardActions sx={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {chunk.source_url ? (
          <Button
            component="a"
            href={chunk.source_url}
            target="_blank"
            rel="noreferrer"
            size="small"
            endIcon={<OpenInNewIcon />}
          >
            SEC filing source
          </Button>
        ) : (
          <span />
        )}
        {!chunk.missing && chunk.corpus_version_id && chunk.ticker && chunk.item && (
          <Button
            component={RouterLink}
            to={`/corpus/${chunk.ticker}/${chunk.item}?corpus=${chunk.corpus_version_id}&chunk=${chunk.chunk_id}`}
            state={{
              origin: {
                to: `${location.pathname}${location.search}`,
                label: 'Evaluation evidence',
              },
            }}
            size="small"
          >
            Open in corpus reader
          </Button>
        )}
        {!chunk.missing && (
          <Button size="small" aria-pressed={selected} onClick={() => onExpand(chunk.chunk_id)}>
            Read full text &amp; provenance
          </Button>
        )}
      </CardActions>
    </Card>
  );
}
function RankedRow({
  chunk,
  open,
  onToggle,
  onExpand,
  selected,
}: {
  chunk: Chunk;
  open: boolean;
  onToggle: () => void;
  onExpand: (id: string) => void;
  selected: boolean;
}) {
  const location = useLocation();
  const citation = chunk.citation || chunk.chunk_id;
  return (
    <Accordion
      expanded={open}
      onChange={onToggle}
      disableGutters
      component="article"
      sx={{
        flexShrink: 0,
        borderColor: selected ? 'primary.main' : chunk.matched ? 'success.main' : 'divider',
        '&:before': { display: 'none' },
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 64 }}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          sx={{ width: '100%', gap: 1, alignItems: { sm: 'center' } }}
        >
          <Typography fontWeight={700} sx={{ minWidth: 58 }}>
            Rank {chunk.rank}
          </Typography>
          <Chip
            size="small"
            color={chunk.matched ? 'success' : 'default'}
            label={chunk.matched ? 'Relevant match' : 'Not matched'}
          />
          <Box sx={{ minWidth: 0 }}>
            <Typography component="code" sx={{ display: 'block', overflowWrap: 'anywhere' }}>
              {citation}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {chunk.ticker} · Item {chunk.item} · {chunk.accession}
            </Typography>
          </Box>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Typography
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            mb: 1,
          }}
        >
          {chunk.preview}
        </Typography>
        <Stack direction="row" sx={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
          {chunk.source_url ? (
            <Button
              component="a"
              href={chunk.source_url}
              target="_blank"
              rel="noreferrer"
              size="small"
              endIcon={<OpenInNewIcon />}
            >
              SEC filing source
            </Button>
          ) : (
            <span />
          )}
          {!chunk.missing && chunk.corpus_version_id && chunk.ticker && chunk.item && (
            <Button
              component={RouterLink}
              to={`/corpus/${chunk.ticker}/${chunk.item}?corpus=${chunk.corpus_version_id}&chunk=${chunk.chunk_id}`}
              state={{
                origin: {
                  to: `${location.pathname}${location.search}`,
                  label: 'Evaluation evidence',
                },
              }}
              size="small"
            >
              Open in corpus reader
            </Button>
          )}
          {!chunk.missing && (
            <Button size="small" aria-pressed={selected} onClick={() => onExpand(chunk.chunk_id)}>
              Read full text &amp; provenance
            </Button>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
export function EvidenceReview({ item }: { item: EvaluationCase }) {
  const location = useLocation();
  const [selectedId, setSelectedId] = useState('');
  const [full, setFull] = useState<FullChunk | null>(null);
  const [loading, setLoading] = useState(false);
  const [openRank, setOpenRank] = useState(item.retrieved[0]?.chunk_id || '');
  const heading = useRef<HTMLHeadingElement>(null);
  const request = useRef(0);
  useEffect(() => {
    if (full) heading.current?.focus();
  }, [full]);
  useEffect(() => {
    setOpenRank(item.retrieved[0]?.chunk_id || '');
    setSelectedId('');
    setFull(null);
    request.current++;
  }, [item.id, item.retrieved]);
  const expand = async (id: string) => {
    const token = ++request.current;
    setSelectedId(id);
    setFull(null);
    setLoading(true);
    try {
      const chunk = await getJson<FullChunk>(`/api/retrieval-evaluations/current/chunks/${id}`);
      if (token === request.current) setFull(chunk);
    } catch {
      if (token === request.current) setFull(null);
    } finally {
      if (token === request.current) setLoading(false);
    }
  };
  const close = () => {
    request.current++;
    setFull(null);
    setSelectedId('');
    setLoading(false);
  };
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
      <section>
        <Typography component="h2" variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Expected filing evidence
        </Typography>
        <Stack spacing={1} sx={{ maxHeight: { xs: 360, md: 520 }, overflowY: 'auto' }}>
          {item.expected.length ? (
            item.expected.map((c) => (
              <ExpectedCard
                key={c.chunk_id}
                chunk={c}
                onExpand={(id) => void expand(id)}
                selected={selectedId === c.chunk_id}
              />
            ))
          ) : (
            <Typography color="text.secondary">No expected evidence was recorded.</Typography>
          )}
        </Stack>
      </section>
      <section>
        <Typography component="h2" variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
          Ranked retrieved evidence
        </Typography>
        <Stack
          data-testid="ranked-evidence-panel"
          spacing={1}
          sx={{
            height: { xs: 360, sm: 420, md: 520 },
            minHeight: 280,
            maxHeight: '75vh',
            overflowY: 'auto',
          }}
        >
          {item.retrieved.length ? (
            item.retrieved.map((c) => (
              <RankedRow
                key={c.chunk_id}
                chunk={c}
                open={openRank === c.chunk_id}
                onToggle={() => setOpenRank((value) => (value === c.chunk_id ? '' : c.chunk_id))}
                onExpand={(id) => void expand(id)}
                selected={selectedId === c.chunk_id}
              />
            ))
          ) : (
            <Typography color="text.secondary">No chunks were retrieved.</Typography>
          )}
        </Stack>
      </section>
      {loading && (
        <Stack role="status" direction="row" sx={{ gap: 1, alignItems: 'center' }}>
          <CircularProgress size={20} />
          Loading full text…
        </Stack>
      )}
      {full && (
        <Card
          component="section"
          aria-label="Selected chunk full text"
          sx={{ gridColumn: '1 / -1', borderColor: 'primary.main' }}
        >
          <CardContent>
            <Stack direction="row" sx={{ justifyContent: 'space-between' }}>
              <Typography
                component="h2"
                variant="h5"
                ref={heading}
                tabIndex={-1}
                sx={{ fontWeight: 700 }}
              >
                Selected chunk: {full.citation || full.chunk_id}
              </Typography>
              <IconButton aria-label="Close full-text inspector" onClick={close}>
                <CloseIcon />
              </IconButton>
            </Stack>
            {full.source_url && (
              <Link href={full.source_url} target="_blank" rel="noreferrer">
                SEC filing source
              </Link>
            )}
            {full.corpus_version_id && full.ticker && full.item && (
              <Button
                component={RouterLink}
                to={`/corpus/${full.ticker}/${full.item}?corpus=${full.corpus_version_id}&chunk=${full.chunk_id}`}
                state={{
                  origin: {
                    to: `${location.pathname}${location.search}`,
                    label: 'Evaluation evidence',
                  },
                }}
              >
                Open in corpus reader
              </Button>
            )}
            <Typography sx={{ my: 2, whiteSpace: 'pre-wrap' }}>{full.text}</Typography>
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                Technical provenance
              </AccordionSummary>
              <AccordionDetails>
                <Box component="pre" sx={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                  {JSON.stringify(
                    { chunk_id: full.chunk_id, provenance: full.provenance },
                    null,
                    2,
                  )}
                </Box>
              </AccordionDetails>
            </Accordion>
          </CardContent>
        </Card>
      )}
      {!loading && selectedId && !full && (
        <Alert severity="error" sx={{ gridColumn: '1 / -1' }}>
          Could not load selected evidence.
        </Alert>
      )}
    </Box>
  );
}
