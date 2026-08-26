import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { EvaluationDashboard } from './pages/EvaluationDashboard';
import { QuestionEvidence } from './pages/QuestionEvidence';
import { Health } from './pages/Health';
import { Research } from './pages/Research';
import { ResearchHistory } from './pages/ResearchHistory';
import { ResearchResult } from './pages/ResearchResult';
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/research" replace />} />
        <Route path="/research" element={<Research />} />
        <Route path="/research/history" element={<ResearchHistory />} />
        <Route path="/research/:id" element={<ResearchResult />} />
        <Route path="/diagnostics/health" element={<Health />} />
        <Route path="/evaluation" element={<EvaluationDashboard />} />
        <Route
          path="/evaluation/configurations/:configurationId/questions/:questionId"
          element={<QuestionEvidence />}
        />
        <Route path="*" element={<Navigate to="/research" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
