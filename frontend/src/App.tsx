import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { RetrievalQuestionResults } from './pages/EvaluationDashboard';
import { EvaluationDashboard } from './pages/EvaluationDashboardSummary';
import { EvaluationOverview } from './pages/EvaluationOverview';
import { GenerationQuestionResults } from './pages/GenerationEvaluationDashboard';
import { GenerationEvaluationDashboard } from './pages/GenerationEvaluationDashboardSummary';
import { GenerationQuestionComparison } from './pages/GenerationQuestionComparison';
import { QuestionEvidence } from './pages/QuestionEvidence';
import { Health } from './pages/Health';
import { Research } from './pages/Research';
import { ResearchHistory } from './pages/ResearchHistory';
import { ResearchResult } from './pages/ResearchResult';
import { CorpusReader, CorpusRoot } from './pages/CorpusReader';
import { Admin, AdminIndex } from './pages/Admin';
import { AdminModelExecutions } from './pages/AdminModelExecutions';
import { AdminUsers } from './pages/AdminUsers';
import { AuthGate, AuthProvider } from './auth';
import { Landing } from './pages/Landing';
import { Privacy, Terms } from './pages/Policies';
import { Overview } from './pages/Overview';
import { HowItWorks } from './pages/HowItWorks';
import { SignIn } from './pages/SignIn';
import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { trackPageView } from './analytics';

function AnalyticsRouteTracker() {
  const location = useLocation();
  useEffect(() => trackPageView(), [location.pathname]);
  return null;
}

export function App({ authenticate = false }: { authenticate?: boolean }) {
  const protectedPage = (page: ReactNode) => (authenticate ? <AuthGate>{page}</AuthGate> : page);
  return (
    <AuthProvider>
      <BrowserRouter>
        <AnalyticsRouteTracker />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/sign-in" element={<SignIn />} />
          <Route path="/research" element={protectedPage(<Research />)} />
          <Route path="/research/history" element={protectedPage(<ResearchHistory />)} />
          <Route path="/research/:id" element={protectedPage(<ResearchResult />)} />
          <Route path="/corpus" element={protectedPage(<CorpusRoot />)} />
          <Route path="/corpus/:ticker/:item" element={protectedPage(<CorpusReader />)} />
          <Route path="/diagnostics/health" element={protectedPage(<Health />)} />
          <Route path="/evaluation" element={<EvaluationOverview />} />
          <Route path="/evaluation/evidence-search" element={<EvaluationDashboard />} />
          <Route path="/evaluation/answer-quality" element={<GenerationEvaluationDashboard />} />
          <Route
            path="/evaluation/evidence-search/questions"
            element={protectedPage(<RetrievalQuestionResults />)}
          />
          <Route
            path="/evaluation/answer-quality/questions"
            element={protectedPage(<GenerationQuestionResults />)}
          />
          <Route
            path="/evaluation/answer-quality/questions/:questionId"
            element={protectedPage(<GenerationQuestionComparison />)}
          />
          <Route path="/admin" element={protectedPage(<Admin />)}>
            <Route index element={<AdminIndex />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="model-executions" element={<AdminModelExecutions />} />
          </Route>
          <Route
            path="/evaluation/evidence-search/configurations/:configurationId/questions/:questionId"
            element={protectedPage(<QuestionEvidence />)}
          />
          <Route path="*" element={<Navigate to="/research" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
