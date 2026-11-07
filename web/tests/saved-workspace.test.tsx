import { afterEach, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { ShortlistPage } from '../components/ShortlistPage';
import { ApiError } from '../lib/api';
vi.mock('../components/AppLayout', () => ({
  AppLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
const memory = {
  version: 0,
  shortlisted_person_ids: [1],
  rejected_person_ids: [2],
  last_query: 'graph learning',
  last_intent: null,
  last_result_ids: [],
};
vi.mock('../lib/session', () => ({
  SESSION_KEY: 'hiresense-session',
  getSession: async () => ({ session_id: 'session1', memory }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
const profile = (id: number) => ({
  person_id: id,
  name: id === 1 ? 'Ada Researcher' : 'Sam Scholar',
  topics: [],
  publications: [],
  claims: [],
  name_sources: [],
});
it('shows saved decisions and session memory together and restores a rejected researcher', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      let body: unknown;
      if (path.endsWith('/authors/1')) body = profile(1);
      else if (path.endsWith('/authors/2')) body = profile(2);
      else if (path.endsWith('/memory')) body = memory;
      else if (path.includes('/decisions/'))
        body = { memory: { ...memory, rejected_person_ids: [] } };
      else throw new Error(`Unexpected ${path} ${init?.method}`);
      return { ok: true, status: 200, json: async () => body } as Response;
    }),
  );
  render(<ShortlistPage />);
  await screen.findByText('Ada Researcher');
  expect(
    screen.getByRole('link', { name: 'Back to home' }).getAttribute('href'),
  ).toBe('/');
  expect(screen.getByText('Your session memory')).toBeTruthy();
  expect(screen.getAllByText('graph learning').length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole('tab', { name: /Rejected/ }));
  const card = (await screen.findByText('Sam Scholar')).closest('article')!;
  fireEvent.click(within(card).getByRole('button', { name: 'Restore' }));
  await waitFor(() => expect(screen.queryByText('Sam Scholar')).toBeNull());
});
it('clears saved state only after deletion is confirmed by the server', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  sessionStorage.setItem('hiresense-session', 'session1');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === 'DELETE')
        return {
          ok: false,
          status: 503,
          json: async () => ({ message: 'Delete failed' }),
        } as Response;
      if (path.includes('/authors/'))
        return {
          ok: true,
          status: 200,
          json: async () => profile(Number(path.split('/').pop())),
        } as Response;
      throw new ApiError('Unexpected request', 500);
    }),
  );
  render(<ShortlistPage />);
  await screen.findByText('Ada Researcher');
  fireEvent.click(screen.getByRole('button', { name: 'Delete session' }));
  await screen.findByRole('alert');
  expect(sessionStorage.getItem('hiresense-session')).toBe('session1');
  expect(screen.getByText('Ada Researcher')).toBeTruthy();
});
