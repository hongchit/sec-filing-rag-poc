import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { EvaluationDashboard } from './pages/EvaluationDashboard';
import { QuestionEvidence } from './pages/QuestionEvidence';
import { Health } from './pages/Health';
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Health />} />
        <Route path="/evaluation" element={<EvaluationDashboard />} />
        <Route
          path="/evaluation/configurations/:configurationId/questions/:questionId"
          element={<QuestionEvidence />}
        />
        <Route path="*" element={<Health />} />
      </Routes>
    </BrowserRouter>
  );
}
