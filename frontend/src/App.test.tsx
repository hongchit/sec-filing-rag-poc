import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import { App } from './main';

test('renders health shell', () => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
  render(<App />);
  expect(screen.getByRole('heading', {name: 'Ingestion foundation'})).toBeInTheDocument();
});
