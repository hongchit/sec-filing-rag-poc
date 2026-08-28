export const corpusItems = ['1', '1A', '3', '7', '7A', '8'] as const;
export type CorpusItem = (typeof corpusItems)[number];

export const itemTitles: Record<CorpusItem, string> = {
  '1': 'Business',
  '1A': 'Risk Factors',
  '3': 'Legal Proceedings',
  '7': 'Management’s Discussion and Analysis',
  '7A': 'Market Risk Disclosures',
  '8': 'Financial Statements',
};

export type CorpusParagraph = {
  index: number;
  start: number;
  end: number;
  text: string;
  is_furniture: boolean;
};
export type HighlightRange = { paragraph_index: number; start: number; end: number };
export type CorpusHighlight = {
  chunk_id: string;
  citation_handle: string;
  char_start: number;
  char_end: number;
  paragraph_start: number;
  paragraph_end: number;
  ranges: HighlightRange[];
};
export type ItemSummary = {
  item: CorpusItem;
  coverage_status: string;
  safe_error: string | null;
  paragraph_count: number;
  character_count: number;
  chunk_count: number;
};
export type CorpusVersion = {
  corpus_version_id: string;
  ticker: string;
  company_name: string | null;
  accession: string;
  form: string;
  filing_date: string;
  report_date: string;
  source_url: string;
  ready_at: string;
  is_active: boolean;
  active_corpus_version_id: string | null;
  items: ItemSummary[];
};
export type CorpusDocument = {
  corpus_version_id: string;
  ticker: string;
  item: CorpusItem;
  coverage_status: string;
  safe_error: string | null;
  source_url: string;
  paragraphs: CorpusParagraph[];
  highlight: CorpusHighlight | null;
};
export type ChunkLocation = {
  chunk_id: string;
  corpus_version_id: string;
  ticker: string;
  item: CorpusItem;
  paragraph_index: number;
  char_start: number;
  char_end: number;
  citation_handle: string;
};

const safeWord = /^[\p{L}\p{N}][\p{L}\p{N}'’.,:;!?()\-–—]*$/u;
export function textFragmentPhrase(text: string): string | null {
  const words = text.trim().split(/\s+/).filter(Boolean);
  for (let start = 0; start < words.length; start++) {
    const available = Math.min(12, words.length - start);
    if (available < 6) break;
    const size = Math.min(10, available);
    const candidate = words.slice(start, start + size);
    if (candidate.every((word) => safeWord.test(word))) return candidate.join(' ');
  }
  return null;
}

export function edgarJump(
  sourceUrl: string,
  paragraphs: CorpusParagraph[],
  currentIndex: number,
): { url: string; approximate: boolean } {
  const selected = paragraphs.find((paragraph) => paragraph.index === currentIndex);
  let phrase = selected ? textFragmentPhrase(selected.text) : null;
  let approximate = false;
  if (!phrase) {
    const position = Math.max(
      0,
      paragraphs.findIndex((p) => p.index === currentIndex),
    );
    for (let distance = 1; distance < paragraphs.length && !phrase; distance++) {
      // Search by document distance, not by length or content score. Trying the
      // following paragraph first makes tie behavior stable and testable.
      for (const candidate of [paragraphs[position + distance], paragraphs[position - distance]]) {
        if (candidate && (phrase = textFragmentPhrase(candidate.text))) {
          approximate = true;
          break;
        }
      }
    }
  }
  const raw = sourceUrl.includes('/ix?doc=')
    ? new URL(sourceUrl).searchParams.get('doc') || sourceUrl
    : sourceUrl;
  const unwrapped = raw.startsWith('/') ? `${new URL(sourceUrl).origin}${raw}` : raw;
  // Text fragments belong on the raw filing document. Retaining an existing hash or
  // the inline-XBRL viewer wrapper would make the jump browser-dependent.
  return {
    url: phrase ? `${unwrapped.split('#')[0]}#:~:text=${encodeURIComponent(phrase)}` : unwrapped,
    approximate,
  };
}

export function isKeyboardTarget(target: EventTarget | null): boolean {
  const element = target instanceof HTMLElement ? target : null;
  return Boolean(
    element?.closest('a,button,input,select,textarea,[contenteditable="true"],[role="button"]'),
  );
}
