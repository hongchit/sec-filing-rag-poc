import { Grid } from '@mui/material';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../authState';
import { signInPath } from '../returnTo';
import { SectionNavigation, type SectionNavigationItem } from './SectionNavigation';

const destinations = [
  ['/evaluation', 'Evaluation overview', false],
  ['/evaluation/evidence-search', 'Retrieval evaluation', false],
  ['/evaluation/evidence-search/questions', 'Evaluation Questions', true],
  ['/evaluation/answer-quality', 'RAG evaluation', false],
  ['/evaluation/answer-quality/questions', 'RAG Answer Comparison', true],
] as const;

export function EvaluationPageLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const auth = useAuth();
  const items: SectionNavigationItem[] = destinations.map(([to, label, protectedPage]) => {
    const locked = protectedPage && auth.status === 'guest';
    return {
      label,
      to: locked ? signInPath(to) : to,
      locked,
      nested: protectedPage,
      active: location.pathname === to,
    };
  });
  return (
    <Grid container spacing={4}>
      <Grid size={{ xs: 12, md: 3 }}>
        <SectionNavigation label="Evaluation" items={items} />
      </Grid>
      <Grid size={{ xs: 12, md: 9 }}>{children}</Grid>
    </Grid>
  );
}
