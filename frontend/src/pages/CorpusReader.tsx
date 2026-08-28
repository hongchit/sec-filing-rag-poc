import ContentCopyIcon from '@mui/icons-material/ContentCopyOutlined';
import LaunchIcon from '@mui/icons-material/LaunchOutlined';
import LinkIcon from '@mui/icons-material/LinkOutlined';
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  Link,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material';
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import {
  Link as RouterLink,
  Navigate,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { errorMessage, getJson } from '../api';
import {
  corpusItems,
  edgarJump,
  isKeyboardTarget,
  itemTitles,
  type ChunkLocation,
  type CorpusDocument,
  type CorpusHighlight,
  type CorpusItem,
  type CorpusVersion,
} from '../corpus';
import type { Company, CompanyStatus } from '../researchTypes';
import { AppShell } from '../components/AppShell';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const chunkHash = /^[0-9a-f]{64}$/;
type Origin = { to: string; label: string };

async function copy(value: string): Promise<void> {
  await navigator.clipboard.writeText(value);
}

export function CorpusRoot() {
  const [target, setTarget] = useState<string>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    // Preserve configured API order so /corpus always chooses the same deterministic
    // landing page; disabled and not-yet-ready companies are skipped.
    getJson<Company[]>('/api/companies')
      .then(async (companies) => {
        for (const company of companies.filter((entry) => entry.enabled)) {
          const status = await getJson<CompanyStatus>(`/api/companies/${company.ticker}/status`);
          if (status.active_corpus) return `/corpus/${company.ticker}/1`;
        }
        throw new Error('No enabled company has a ready active corpus.');
      })
      .then(setTarget)
      .catch(() => setFailed(true));
  }, []);
  if (target) return <Navigate replace to={target} />;
  return (
    <AppShell>
      <Alert severity={failed ? 'info' : 'info'} aria-live="polite">
        {failed
          ? 'No readable corpus is currently available.'
          : 'Finding the first readable corpus…'}
      </Alert>
    </AppShell>
  );
}

function markedText(text: string, ranges: Array<{ start: number; end: number }>) {
  if (!ranges.length) return text;
  const output = [];
  let cursor = 0;
  for (const range of ranges) {
    output.push(text.slice(cursor, range.start));
    output.push(
      <mark key={`${range.start}-${range.end}`}>{text.slice(range.start, range.end)}</mark>,
    );
    cursor = range.end;
  }
  output.push(text.slice(cursor));
  return output;
}

export function CorpusReader() {
  const { ticker = '', item = '' } = useParams();
  const [search] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const corpusParam = search.get('corpus');
  const chunkParam = search.get('chunk');
  const [companies, setCompanies] = useState<Company[]>([]);
  const [status, setStatus] = useState<CompanyStatus>();
  const [version, setVersion] = useState<CorpusVersion>();
  const [document, setDocument] = useState<CorpusDocument>();
  const [highlight, setHighlight] = useState<CorpusHighlight | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [visible, setVisible] = useState(1);
  const paragraphRefs = useRef<Record<number, HTMLElement | null>>({});
  const retainedChunk = useRef<{ corpus: string; item: string } | null>(null);
  const origin = (location.state as { origin?: Origin } | null)?.origin;
  const originState = useMemo(() => (origin ? { origin } : undefined), [origin]);
  const normalizedTicker = ticker.toUpperCase();
  const validItem = corpusItems.includes(item as CorpusItem);

  useEffect(() => {
    getJson<Company[]>('/api/companies')
      .then(setCompanies)
      .catch(() => setCompanies([]));
  }, []);
  useEffect(() => {
    if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(normalizedTicker)) return;
    getJson<CompanyStatus>(`/api/companies/${normalizedTicker}/status`)
      .then(setStatus)
      .catch(() => setStatus(undefined));
  }, [normalizedTicker]);

  useEffect(() => {
    let cancelled = false;
    // The chunk URL is replaced by a paragraph URL after focus. Keep the already
    // loaded ranges through that render instead of immediately fetching a plain Item.
    if (
      !chunkParam &&
      corpusParam &&
      retainedChunk.current?.corpus === corpusParam &&
      retainedChunk.current.item === item
    )
      return;
    setError('');
    setVersion(undefined);
    setDocument(undefined);
    setHighlight(null);
    setVisible(1);
    async function load() {
      if (
        !validItem ||
        (corpusParam && !uuid.test(corpusParam)) ||
        (chunkParam && !chunkHash.test(chunkParam))
      )
        throw new Error('This corpus address is invalid.');
      let corpusId = corpusParam;
      if (chunkParam) {
        // Location is authoritative for all route components. This also prevents a
        // valid chunk from being shown under a misleading ticker or Item URL.
        const located = await getJson<ChunkLocation>(`/api/corpus/chunks/${chunkParam}/location`);
        corpusId = located.corpus_version_id;
        if (ticker !== located.ticker || item !== located.item || corpusParam !== corpusId) {
          void navigate(
            `/corpus/${located.ticker}/${located.item}?corpus=${corpusId}&chunk=${chunkParam}`,
            { replace: true, state: originState },
          );
          return;
        }
      }
      if (!corpusId) {
        const companyStatus = await getJson<CompanyStatus>(
          `/api/companies/${normalizedTicker}/status`,
        );
        corpusId = companyStatus.active_corpus?.corpus_version_id ?? null;
      }
      if (!corpusId) throw new Error('This company has no ready corpus.');
      const metadata = await getJson<CorpusVersion>(`/api/corpus/versions/${corpusId}`);
      if (metadata.ticker !== normalizedTicker) {
        // A pinned corpus UUID outranks the human-readable ticker segment.
        void navigate(
          `/corpus/${metadata.ticker}/${item}?corpus=${corpusId}${chunkParam ? `&chunk=${chunkParam}` : ''}`,
          { replace: true, state: originState },
        );
        return;
      }
      const payload = await getJson<CorpusDocument>(
        `/api/corpus/versions/${corpusId}/items/${item}${chunkParam ? `?chunk_id=${chunkParam}` : ''}`,
      );
      if (cancelled) return;
      // Route changes can finish requests out of order. Never allow an obsolete
      // response to overwrite the document selected by the current URL.
      setVersion(metadata);
      setDocument(payload);
      setHighlight(payload.highlight);
      retainedChunk.current = payload.highlight ? { corpus: corpusId, item } : null;
    }
    load().catch((reason: unknown) => !cancelled && setError(errorMessage(reason)));
    return () => {
      cancelled = true;
    };
  }, [corpusParam, chunkParam, item, navigate, normalizedTicker, originState, ticker, validItem]);

  useEffect(() => {
    if (!document) return;
    const requested = highlight?.paragraph_start ?? Number(location.hash.match(/^#p-(\d+)$/)?.[1]);
    if (!requested) {
      window.scrollTo({ top: 0 });
      return;
    }
    const node = paragraphRefs.current[requested];
    if (!node) return;
    node.scrollIntoView({
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'center',
    });
    node.focus({ preventScroll: true });
    setVisible(requested);
    if (chunkParam && version) {
      // Replace rather than push: Back should return to the citation source, not to
      // an intermediate URL containing the transient chunk instruction.
      void navigate(
        `/corpus/${version.ticker}/${document.item}?corpus=${version.corpus_version_id}#p-${requested}`,
        { replace: true, state: originState },
      );
    }
  }, [chunkParam, document, highlight, location.hash, navigate, originState, version]);

  useEffect(() => {
    if (!document || !('IntersectionObserver' in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (first) setVisible(Number(first.target.id.slice(2)));
      },
      { rootMargin: '-20% 0px -70% 0px' },
    );
    // Visible-paragraph state drives labels and copy/EDGAR actions only. Deliberately
    // leave the hash unchanged during ordinary scrolling to avoid noisy history.
    Object.values(paragraphRefs.current).forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
  }, [document]);

  const selectedIndex = corpusItems.indexOf(item as CorpusItem);
  const goItem = (nextItem: CorpusItem) => {
    retainedChunk.current = null;
    setHighlight(null);
    const query =
      version && (corpusParam || !version.is_active) ? `?corpus=${version.corpus_version_id}` : '';
    void navigate(`/corpus/${version?.ticker ?? normalizedTicker}/${nextItem}${query}`, {
      state: originState,
    });
  };
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      // Do not steal browser shortcuts or keystrokes intended for an interactive or
      // editable control. Unmodified reader-level keys alone traverse Items.
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        isKeyboardTarget(event.target)
      )
        return;
      if ((event.key === 'ArrowLeft' || event.key === '[') && selectedIndex > 0) {
        event.preventDefault();
        goItem(corpusItems[selectedIndex - 1]);
      }
      if (
        (event.key === 'ArrowRight' || event.key === ']') &&
        selectedIndex < corpusItems.length - 1
      ) {
        event.preventDefault();
        goItem(corpusItems[selectedIndex + 1]);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  });

  const jump = useMemo(
    () => (document ? edgarJump(document.source_url, document.paragraphs, visible) : null),
    [document, visible],
  );
  const versions = status
    ? [status.active_corpus, ...status.historical_corpora].filter(Boolean)
    : [];
  const share = (paragraph = visible) =>
    `${window.location.origin}/corpus/${version?.ticker ?? normalizedTicker}/${item}?corpus=${version?.corpus_version_id}#p-${paragraph}`;
  const announceCopy = (promise: Promise<void>, success: string): void => {
    void promise
      .then(() => setNotice(success))
      .catch(() => setNotice('Copy failed. Your browser may have blocked clipboard access.'));
  };

  if (error)
    return (
      <AppShell>
        <Alert severity="warning">
          <Typography variant="h5">Corpus page not found</Typography>
          <Typography>{error}</Typography>
          <Button component={RouterLink} to="/corpus">
            Choose an available corpus
          </Button>
        </Alert>
      </AppShell>
    );
  if (!version || !document)
    return (
      <AppShell>
        <Stack direction="row" role="status" spacing={1}>
          <CircularProgress size={22} />
          <Typography>Loading corpus reader…</Typography>
        </Stack>
      </AppShell>
    );

  const summary = version.items.find((entry) => entry.item === item)!;
  const originCrumb = origin && (
    <Link component={RouterLink} to={origin.to}>
      {origin.label}
    </Link>
  );
  const traversal = (
    <Stack direction="row" justifyContent="space-between">
      <Button
        disabled={selectedIndex <= 0}
        onClick={() => goItem(corpusItems[selectedIndex - 1])}
        startIcon={<NavigateBeforeIcon />}
      >
        Previous Item
      </Button>
      <Button
        disabled={selectedIndex >= corpusItems.length - 1}
        onClick={() => goItem(corpusItems[selectedIndex + 1])}
        endIcon={<NavigateNextIcon />}
      >
        Next Item
      </Button>
    </Stack>
  );
  return (
    <AppShell maxWidth="xl">
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '260px minmax(0, 1fr)' },
          gap: 4,
        }}
      >
        <Stack
          component="aside"
          spacing={2}
          sx={{ alignSelf: 'start', position: { md: 'sticky' }, top: 16 }}
        >
          <FormControl fullWidth>
            <InputLabel>Company</InputLabel>
            <Select
              label="Company"
              value={version.ticker}
              onChange={(event) => void navigate(`/corpus/${event.target.value}/${item}`)}
            >
              {companies
                .filter((company) => company.enabled && company.corpus_status === 'ready')
                .map((company) => (
                  <MenuItem key={company.ticker} value={company.ticker}>
                    {company.ticker} — {company.name}
                  </MenuItem>
                ))}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel>Filing version</InputLabel>
            <Select
              label="Filing version"
              value={version.corpus_version_id}
              onChange={(event) =>
                void navigate(`/corpus/${version.ticker}/${item}?corpus=${event.target.value}`)
              }
            >
              {versions.map(
                (corpus) =>
                  corpus && (
                    <MenuItem key={corpus.corpus_version_id} value={corpus.corpus_version_id}>
                      {corpus.report_date.slice(0, 4)} · {corpus.accession}
                      {corpus.corpus_version_id === status?.active_corpus?.corpus_version_id
                        ? ' (active)'
                        : ''}
                    </MenuItem>
                  ),
              )}
            </Select>
          </FormControl>
          <Paper variant="outlined">
            <List aria-label="Filing Items" disablePadding>
              {version.items.map((entry) => (
                <ListItemButton
                  key={entry.item}
                  selected={entry.item === item}
                  aria-current={entry.item === item ? 'page' : undefined}
                  onClick={() => goItem(entry.item)}
                >
                  <ListItemText
                    primary={`Item ${entry.item}`}
                    secondary={`${itemTitles[entry.item]} · ${entry.paragraph_count} paragraphs${entry.coverage_status !== 'present' ? ` · ${entry.coverage_status.replaceAll('_', ' ')}` : ''}`}
                  />
                </ListItemButton>
              ))}
            </List>
          </Paper>
        </Stack>
        <Box sx={{ minWidth: 0 }}>
          <Breadcrumbs aria-label="Breadcrumb" sx={{ mb: 2 }}>
            {originCrumb}
            <Link component={RouterLink} to="/corpus">
              Corpus
            </Link>
            <Typography>
              {version.ticker} Item {item}
            </Typography>
          </Breadcrumbs>
          {!version.is_active && (
            <Alert severity="info" sx={{ mb: 2 }}>
              You are reading a historical corpus version.{' '}
              {version.active_corpus_version_id && (
                <Link component={RouterLink} to={`/corpus/${version.ticker}/${item}`}>
                  Open the active version
                </Link>
              )}
            </Alert>
          )}
          <Paper sx={{ p: 2, mb: 2, position: 'sticky', top: 0, zIndex: 2 }}>
            <Typography variant="h2">
              {version.ticker} · 10-K FY{version.report_date.slice(0, 4)} · Item {item} —{' '}
              {itemTitles[item as CorpusItem]}
            </Typography>
            <Typography color="text.secondary">
              Paragraph {visible} · filed {version.filing_date} · accession {version.accession}
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
              <Button
                component="a"
                href={jump?.url}
                target="_blank"
                rel="noreferrer"
                startIcon={<LaunchIcon />}
              >
                Open on EDGAR{jump?.approximate ? ' (approximate jump)' : ' — jump to paragraph'}
              </Button>
              <Button
                startIcon={<LinkIcon />}
                onClick={() => announceCopy(copy(share()), 'Paragraph link copied.')}
              >
                Copy link
              </Button>
            </Stack>
          </Paper>
          {traversal}
          {highlight && (
            <Alert severity="info" sx={{ my: 2 }}>
              Retrieved chunk <code>{highlight.citation_handle}</code> covers characters{' '}
              {highlight.char_start.toLocaleString()}–{highlight.char_end.toLocaleString()} of Item{' '}
              {item}.
            </Alert>
          )}
          {['7', '7A', '8'].includes(item) && (
            <Alert severity="info" sx={{ my: 2 }}>
              Tables are preserved as indexed plain text and are usually easier to read in the
              original EDGAR filing.
            </Alert>
          )}
          {summary.coverage_status !== 'present' ? (
            <Alert severity="warning" sx={{ my: 2 }}>
              <Typography variant="h5">
                Item {item} is {summary.coverage_status.replaceAll('_', ' ')}
              </Typography>
              <Typography>
                {summary.safe_error || 'No source text was recorded for this Item.'}
              </Typography>
            </Alert>
          ) : (
            <Box
              component="article"
              aria-label={`Item ${item} full text`}
              sx={{ maxWidth: '72ch', mx: 'auto', py: 2 }}
            >
              {document.paragraphs.map((paragraph) => {
                const ranges =
                  highlight?.ranges.filter((range) => range.paragraph_index === paragraph.index) ??
                  [];
                return (
                  <Fragment key={paragraph.index}>
                    <Box
                      component="section"
                      sx={{
                        position: 'relative',
                        opacity: paragraph.is_furniture ? 0.58 : 1,
                        '&:hover .paragraph-actions, &:focus-within .paragraph-actions': {
                          opacity: 1,
                        },
                      }}
                    >
                      <Typography
                        component="p"
                        id={`p-${paragraph.index}`}
                        ref={(node) => {
                          paragraphRefs.current[paragraph.index] = node;
                        }}
                        tabIndex={-1}
                        sx={{
                          whiteSpace: 'pre-wrap',
                          lineHeight: 1.75,
                          my: paragraph.is_furniture ? 1 : 2,
                        }}
                      >
                        {markedText(paragraph.text, ranges)}
                      </Typography>
                      <Stack
                        className="paragraph-actions"
                        direction="row"
                        sx={{ opacity: { xs: 1, md: 0 }, transition: 'opacity .15s', mb: 1 }}
                      >
                        <Button
                          size="small"
                          startIcon={<LinkIcon />}
                          onClick={() =>
                            announceCopy(copy(share(paragraph.index)), 'Paragraph link copied.')
                          }
                        >
                          Copy paragraph link
                        </Button>
                        <Button
                          size="small"
                          startIcon={<ContentCopyIcon />}
                          onClick={() =>
                            announceCopy(copy(paragraph.text), 'Paragraph text copied.')
                          }
                        >
                          Copy text
                        </Button>
                      </Stack>
                    </Box>
                    <Divider />
                  </Fragment>
                );
              })}
            </Box>
          )}
          {traversal}
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            If the exact EDGAR jump is unsupported, use the filing table of contents or copy
            paragraph text and find it in the filing. Exact jumps are acceptance-tested in Chromium.
          </Typography>
        </Box>
      </Box>
      <Snackbar
        open={Boolean(notice)}
        autoHideDuration={3500}
        onClose={() => setNotice('')}
        message={notice}
      />
    </AppShell>
  );
}
