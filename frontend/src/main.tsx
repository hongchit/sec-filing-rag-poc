import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

export function App() {
  const [status, setStatus] = React.useState('Checking API…');
  React.useEffect(() => { fetch('/api/health').then(r => r.ok ? r.json() : Promise.reject()).then(() => setStatus('API and database ready')).catch(() => setStatus('API unavailable')); }, []);
  return <main><p className="eyebrow">SEC Filing RAG</p><h1>Ingestion and retrieval foundation</h1><p>Versioned latest and historical 10-K corpora with traceable SEC provenance.</p><output aria-live="polite">{status}</output></main>;
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
