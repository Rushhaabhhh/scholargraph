import { afterEach, describe, expect, it, vi } from 'vitest';
import { getSession, SESSION_KEY } from '../lib/session';

const memory = {
  version: 0,
  shortlisted_person_ids: [],
  rejected_person_ids: [],
  last_query: null,
  last_intent: null,
  last_result_ids: [],
};
const response = (status: number, body: unknown) =>
  ({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  }) as Response;
afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe('session recovery', () => {
  it.each([
    [404, 'session_not_found'],
    [409, 'session_graph_mismatch'],
  ])('creates a new session after %s / %s', async (status, code) => {
    sessionStorage.setItem(SESSION_KEY, 'old-session');
    sessionStorage.setItem('scholargraph-results', 'stale results');
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        response(status, { code, message: 'Old session unavailable' }),
      )
      .mockResolvedValueOnce(
        response(200, { session_id: 'new-session', memory }),
      );
    vi.stubGlobal('fetch', fetcher);
    const result = await getSession();
    expect(result.session_id).toBe('new-session');
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('new-session');
    expect(sessionStorage.getItem('scholargraph-results')).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it('keeps the existing session when the backend is temporarily unavailable', async () => {
    sessionStorage.setItem(SESSION_KEY, 'old-session');
    const fetcher = vi.fn().mockResolvedValue(
      response(503, {
        code: 'backend_unavailable',
        message: 'Backend unavailable',
      }),
    );
    vi.stubGlobal('fetch', fetcher);
    await expect(getSession()).rejects.toThrow('Backend unavailable');
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('old-session');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it('shares session creation across concurrent initializations', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(response(200, { session_id: 'new-session', memory }));
    vi.stubGlobal('fetch', fetcher);
    const [first, second] = await Promise.all([getSession(), getSession()]);
    expect(first.session_id).toBe('new-session');
    expect(second.session_id).toBe('new-session');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
