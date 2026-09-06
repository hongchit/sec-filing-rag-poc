import type { Cases, EvaluationCase } from './types';

export const PAGE_SIZE = 25;

export type EvaluationQuery = {
  outcome: string;
  company: string;
  item: string;
  goal: string;
  queryType: string;
  search: string;
  page: number;
  sort: string;
  direction: 'asc' | 'desc';
  configuration: string;
};

export function readEvaluationQuery(params: URLSearchParams): EvaluationQuery {
  const sort = params.get('sort') || 'official';
  return {
    outcome: params.get('outcome') || '',
    company: params.get('company') || '',
    item: params.get('item') || '',
    goal: params.get('goal') || '',
    queryType: params.get('query_type') || '',
    search: params.get('q') || '',
    page: Number(params.get('page')) || 1,
    sort,
    direction:
      (params.get('sort_direction') as 'asc' | 'desc') ||
      (sort === 'official' || sort === 'latency' ? 'asc' : 'desc'),
    configuration: params.get('configuration') || '',
  };
}

export function filterCases(cases: EvaluationCase[], query: EvaluationQuery) {
  return cases.filter(
    (c) =>
      (!query.outcome || c.outcome === query.outcome) &&
      (!query.company || c.ticker === query.company) &&
      (!query.item || c.items.includes(query.item)) &&
      (!query.goal || c.goal === query.goal) &&
      (!query.queryType || c.query_type === query.queryType) &&
      c.question.toLowerCase().includes(query.search.toLowerCase()),
  );
}

export function detailPath(
  configurationId: string,
  questionId: string,
  params: URLSearchParams,
  page?: number,
) {
  const next = new URLSearchParams(params);
  next.set('configuration', configurationId);
  if (page) next.set('page', String(page));
  return `/evaluation/evidence-search/configurations/${encodeURIComponent(configurationId)}/questions/${encodeURIComponent(questionId)}?${next}`;
}

export function overviewPath(params: URLSearchParams) {
  return `/evaluation/evidence-search/questions${params.size ? `?${params}` : ''}`;
}

export function casePage(cases: Cases, questionId: string, query: EvaluationQuery) {
  const index = filterCases(cases.cases, query).findIndex((value) => value.id === questionId);
  return index < 0 ? 1 : Math.floor(index / PAGE_SIZE) + 1;
}

export function researchPath(question: {
  ticker: string;
  question: string;
  goal: string;
  items: string[];
  accession?: string;
}) {
  const params = new URLSearchParams({
    company: question.ticker,
    goal: question.goal === 'legal_and_regulatory_risk' ? 'legal_regulatory_risk' : question.goal,
    items: question.items.join(','),
    question: question.question,
  });
  if (question.accession) params.set('accession', question.accession);
  return `/research?${params}`;
}
