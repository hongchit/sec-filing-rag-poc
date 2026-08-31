import { Tab, Tabs } from '@mui/material';
import { Link as RouterLink, useLocation } from 'react-router-dom';

export function EvaluationNav() {
  const location = useLocation();
  const active = location.pathname.startsWith('/evaluation/generation')
    ? 'generation'
    : 'retrieval';
  return (
    <Tabs value={active} aria-label="Evaluation sections" variant="scrollable">
      <Tab value="retrieval" label="Retrieval" component={RouterLink} to="/evaluation" />
      <Tab
        value="generation"
        label="RAG generation"
        component={RouterLink}
        to="/evaluation/generation"
      />
    </Tabs>
  );
}
