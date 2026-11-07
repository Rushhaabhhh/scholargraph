import { api, ApiError } from './api';
import type { Memory } from './types';
export const SESSION_KEY = 'hiresense-session';
export type SessionInfo = { session_id: string; memory: Memory };
let pending: Promise<SessionInfo> | null = null;
async function loadSession(): Promise<SessionInfo> {
  let id =
    typeof window === 'undefined' ? null : sessionStorage.getItem(SESSION_KEY);
  if (id) {
    try {
      return {
        session_id: id,
        memory: await api<Memory>(`/sessions/${id}/memory`),
      };
    } catch (error) {
      if (
        !(error instanceof ApiError) ||
        (error.status !== 404 && error.code !== 'session_graph_mismatch')
      )
        throw error;
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem('hiresense-results');
      sessionStorage.removeItem('scholargraph-results');
    }
  }
  const session = await api<SessionInfo>('/sessions', { method: 'POST' });
  sessionStorage.setItem(SESSION_KEY, session.session_id);
  return session;
}
export function getSession(): Promise<SessionInfo> {
  if (!pending)
    pending = loadSession().finally(() => {
      pending = null;
    });
  return pending;
}
