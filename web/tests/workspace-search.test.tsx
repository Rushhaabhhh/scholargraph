import { afterEach, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { Workspace } from '../components/Workspace';

vi.mock('../components/AppLayout', () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../components/ResearchHero', () => ({ ResearchHero: () => null }));
vi.mock('../components/CursorSwarm', () => ({ CursorSwarm: () => null }));
vi.mock('../components/PipelineStory', () => ({ PipelineStory: () => null }));
vi.mock('../components/EvidenceGraph', () => ({ EvidenceGraph: () => null }));
vi.mock('../components/AssistantDialog', () => ({
  AssistantDialog: () => null,
}));
vi.mock('../lib/session', () => ({
  getSession: async () => ({ session_id: 'test', memory }),
}));
const memory = {
  version: 0,
  shortlisted_person_ids: [],
  rejected_person_ids: [],
  last_query: null,
  last_intent: null,
  last_result_ids: [],
};
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

it('infers query dates by default and sends an explicit any-time override', async () => {
  const calls: Record<string, unknown>[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      let data: unknown;
      if (path.endsWith('/health'))
        data = {
          status: 'ok',
          papers: 1,
          authors: 1,
          model_version: 'test',
          query_provider: 'fallback',
        };
      else if (path.endsWith('/memory')) data = memory;
      else {
        const payload = JSON.parse(String(init?.body));
        calls.push(payload);
        data = {
          query: payload.query,
          retrieval_query: 'graph retrieval',
          results: [],
          memory,
          understanding: {
            intent: {
              topics: ['graph retrieval'],
              recency_preference: 'any',
              since_year: payload.recency_preference === 'any' ? null : 2018,
            },
            provider: 'fallback',
          },
          effective_filters: {
            graph_cutoff_year: 2019,
            since_year: payload.recency_preference === 'any' ? null : 2018,
          },
        };
      }
      return { ok: true, status: 200, json: async () => data } as Response;
    }),
  );
  Element.prototype.scrollIntoView = vi.fn();
  render(<Workspace />);
  const input = screen.getByLabelText('RESEARCH QUESTION OR TOPIC');
  fireEvent.change(input, { target: { value: 'graph retrieval since 2018' } });
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: /Find researchers/ }),
    ).not.toHaveProperty('disabled', true),
  );
  fireEvent.click(screen.getByRole('button', { name: /Find researchers/ }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].recency_preference).toBeNull();
  expect(calls[0].since_year).toBeNull();
  await screen.findByText('Since 2018');
  fireEvent.change(screen.getByLabelText('Publication activity'), {
    target: { value: 'any' },
  });
  fireEvent.click(screen.getByRole('button', { name: /Find researchers/ }));
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[1].recency_preference).toBe('any');
});
