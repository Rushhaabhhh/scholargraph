'use client';
import { useEffect, useState } from 'react';
import { AppLayout } from './AppLayout';
import { api, ApiError } from '../lib/api';
import { getSession } from '../lib/session';
import type { Memory } from '../lib/types';
export function SettingsPage() {
  const [session, setSession] = useState('');
  const [memory, setMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  async function load() {
    setLoading(true);
    try {
      const info = await getSession();
      setSession(info.session_id);
      setMemory(info.memory);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function deleteAll() {
    if (
      !session ||
      !window.confirm(
        'Delete this session and all its saved decisions? This cannot be undone.',
      )
    )
      return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api<void>(`/sessions/${session}`, { method: 'DELETE' });
      sessionStorage.removeItem('hiresense-session');
      sessionStorage.removeItem('hiresense-results');
      sessionStorage.removeItem('scholargraph-results');
      setSession('');
      setMemory(null);
      setNotice(
        'Session memory deleted. A new session will be created when you search again.',
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) {
        try {
          await api<Memory>(`/sessions/${session}/memory`);
          throw new Error(
            'The server did not confirm deletion. Your memory remains saved.',
          );
        } catch (verify) {
          if (verify instanceof ApiError && verify.status === 404) {
            sessionStorage.removeItem('hiresense-session');
            sessionStorage.removeItem('hiresense-results');
            sessionStorage.removeItem('scholargraph-results');
            setSession('');
            setMemory(null);
            setNotice('Session memory deleted.');
          } else setError((verify as Error).message);
        }
      } else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <AppLayout>
      <section className="settings-page">
        <div className="page-heading">
          <div>
            <span className="eyebrow">PREFERENCES & PRIVACY</span>
            <h1>Settings</h1>
            <p>Review what this research session remembers.</p>
          </div>
        </div>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button onClick={load}>Retry</button>
          </div>
        )}
        {notice && (
          <div className="success-banner" role="status">
            ✓ &nbsp;{notice}
          </div>
        )}
        <section className="settings-card">
          <div>
            <span className="eyebrow">ASSISTANT MEMORY</span>
            <h2>Your session decisions</h2>
            <p>
              The assistant uses your shortlist, rejected experts and last
              search to interpret follow-up commands. It does not keep a
              separate editable profile.
            </p>
          </div>
          {loading ? (
            <div className="state" role="status">
              Loading memory…
            </div>
          ) : (
            <>
              <div className="settings-stats">
                <div>
                  <strong>{memory?.shortlisted_person_ids.length ?? 0}</strong>
                  <span>SHORTLISTED</span>
                </div>
                <div>
                  <strong>{memory?.rejected_person_ids.length ?? 0}</strong>
                  <span>REJECTED</span>
                </div>
                <div>
                  <strong>{memory?.last_query ? 'Active' : 'Empty'}</strong>
                  <span>SEARCH CONTEXT</span>
                </div>
              </div>
              <div className="memory-detail">
                <strong>Last research query</strong>
                <p>{memory?.last_query || 'No query stored.'}</p>
                <strong>Saved shortlist IDs</strong>
                <p>{memory?.shortlisted_person_ids.join(', ') || 'None'}</p>
                <strong>Rejected IDs</strong>
                <p>{memory?.rejected_person_ids.join(', ') || 'None'}</p>
              </div>
              <div className="settings-danger">
                <div>
                  <strong>Delete session memory</strong>
                  <p>
                    Removes saved decisions and conversation context for this
                    browser session.
                  </p>
                </div>
                <button
                  className="danger-button"
                  disabled={busy || !session}
                  onClick={deleteAll}
                >
                  {busy ? 'Deleting…' : 'Delete session'}
                </button>
              </div>
            </>
          )}
        </section>
        <p className="settings-footnote">
          This is a local assignment demo. It has no user accounts, organization
          membership, or cross-user profile preferences.
        </p>
      </section>
    </AppLayout>
  );
}
