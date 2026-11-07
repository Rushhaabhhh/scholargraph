'use client';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowUpRight,
  Bookmark,
  Search,
  ShieldCheck,
  Trash2,
  Users,
} from 'lucide-react';
import { AppLayout } from './AppLayout';
import { api, ApiError, json, requestId } from '../lib/api';
import { getSession, SESSION_KEY } from '../lib/session';
import type { Memory, Profile } from '../lib/types';

export function ShortlistPage() {
  const [session, setSession] = useState('');
  const [memory, setMemory] = useState<Memory | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [tab, setTab] = useState<'shortlist' | 'rejected'>('shortlist');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [missing, setMissing] = useState<number[]>([]);
  async function load() {
    setLoading(true);
    try {
      const current = await getSession();
      setSession(current.session_id);
      setMemory(current.memory);
      const ids = [
        ...new Set([
          ...current.memory.shortlisted_person_ids,
          ...current.memory.rejected_person_ids,
        ]),
      ];
      const values = await Promise.all(
        ids.map((id) => api<Profile>(`/authors/${id}`).catch(() => null)),
      );
      setProfiles(values.filter((x): x is Profile => x !== null));
      setMissing(ids.filter((_, i) => values[i] === null));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  const ids =
    tab === 'shortlist'
      ? memory?.shortlisted_person_ids || []
      : memory?.rejected_person_ids || [];
  const rows = useMemo(
    () =>
      ids
        .map((id) => profiles.find((p) => p.person_id === id))
        .filter((p): p is Profile => !!p)
        .filter((p) => p.name.toLowerCase().includes(search.toLowerCase())),
    [ids, profiles, search],
  );
  async function decision(id: number, value: 'shortlist' | 'reject' | 'clear') {
    if (!session || !memory) return;
    setBusy(true);
    setError('');
    try {
      const fresh = await api<Memory>(`/sessions/${session}/memory`);
      const result = await api<{ memory: Memory }>(
        `/sessions/${session}/decisions/${id}`,
        json('PUT', {
          decision: value,
          expected_version: fresh.version,
          request_id: requestId(),
        }),
      );
      setMemory(result.memory);
      setSelected((xs) => xs.filter((x) => x !== id));
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? 'Session changed in another view. Refresh and retry.'
          : (e as Error).message,
      );
      void load();
    } finally {
      setBusy(false);
    }
  }
  async function deleteSession() {
    if (
      !session ||
      !window.confirm(
        'Delete this search session and all its saved decisions? This cannot be undone.',
      )
    )
      return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      try {
        await api<void>(`/sessions/${session}`, { method: 'DELETE' });
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 0) throw e;
        try {
          await api<Memory>(`/sessions/${session}/memory`);
        } catch (verify) {
          if (verify instanceof ApiError && verify.status === 404) {
            clearSession();
            return;
          }
          throw verify;
        }
        throw new Error(
          'The server did not confirm deletion. Your memory remains saved.',
        );
      }
      clearSession();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function clearSession() {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem('hiresense-results');
    sessionStorage.removeItem('scholargraph-results');
    sessionStorage.removeItem('scholargraph-filters');
    setSession('');
    setMemory(null);
    setProfiles([]);
    setSelected([]);
    setMissing([]);
    setNotice(
      'Session memory deleted. A new session will be created when you search again.',
    );
  }
  const comparisons = profiles.filter((p) => selected.includes(p.person_id));
  return (
    <AppLayout>
      <main className="saved-page saved-workspace">
        <Link className="saved-back-home" href="/">
          <ArrowLeft size={16} /> Back to home
        </Link>
        <header className="saved-workspace-header">
          <div>
            <span className="eyebrow">YOUR RESEARCH WORKSPACE</span>
            <h1>
              Saved & session<span>.</span>
            </h1>
            <p>
              Your researchers, decisions and search memory, all in one place.
            </p>
          </div>
          <Link className="saved-find" href="/#search">
            Find researchers <ArrowUpRight size={18} />
          </Link>
        </header>
        {error && (
          <div role="alert" className="error-banner">
            {error} <button onClick={() => void load()}>Try again</button>
          </div>
        )}
        {notice && (
          <div role="status" className="saved-notice">
            {notice}
          </div>
        )}
        <div className="saved-overview" aria-label="Session overview">
          <div>
            <Bookmark size={19} />
            <span>SHORTLISTED</span>
            <strong>
              {memory?.shortlisted_person_ids.length ?? (loading ? '—' : 0)}
            </strong>
            <small>Researchers to revisit</small>
          </div>
          <div>
            <Users size={19} />
            <span>REJECTED</span>
            <strong>
              {memory?.rejected_person_ids.length ?? (loading ? '—' : 0)}
            </strong>
            <small>Available to restore</small>
          </div>
          <div>
            <Search size={19} />
            <span>LAST SEARCH</span>
            <strong className="saved-overview-query">
              {memory?.last_query || 'No search yet'}
            </strong>
            <small>Used as session context</small>
          </div>
        </div>
        <section className="saved-section" aria-labelledby="saved-heading">
          <div className="saved-section-heading">
            <div>
              <span className="eyebrow">YOUR PEOPLE</span>
              <h2 id="saved-heading">Researcher decisions</h2>
              <p>
                Review your shortlist or restore someone you previously
                rejected.
              </p>
            </div>
            <span className="saved-section-label">SAVED IN THIS SESSION</span>
          </div>
          <div className="saved-toolbar">
            <div
              className="saved-tabs"
              role="tablist"
              aria-label="Expert decisions"
            >
              <button
                role="tab"
                aria-selected={tab === 'shortlist'}
                className={tab === 'shortlist' ? 'selected' : ''}
                onClick={() => {
                  setTab('shortlist');
                  setSelected([]);
                }}
              >
                Shortlisted{' '}
                <span>{memory?.shortlisted_person_ids.length ?? 0}</span>
              </button>
              <button
                role="tab"
                aria-selected={tab === 'rejected'}
                className={tab === 'rejected' ? 'selected' : ''}
                onClick={() => {
                  setTab('rejected');
                  setSelected([]);
                }}
              >
                Rejected <span>{memory?.rejected_person_ids.length ?? 0}</span>
              </button>
            </div>
            <div className="saved-search-wrap">
              <Search size={17} aria-hidden="true" />
              <label className="sr-only" htmlFor="saved-search">
                Search saved experts
              </label>
              <input
                id="saved-search"
                className="saved-search"
                placeholder="Search by name"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
          {busy && (
            <p className="saved-saving" role="status">
              Saving changes…
            </p>
          )}
          {missing.some((id) => ids.includes(id)) && (
            <p className="saved-warning" role="status">
              Some saved profiles could not be loaded.{' '}
              <button onClick={() => void load()}>
                Retry loading profiles
              </button>
            </p>
          )}
          {loading ? (
            <div className="saved-empty">
              <p role="status">Loading your researchers…</p>
            </div>
          ) : rows.length === 0 ? (
            <div className="saved-empty">
              <div className="saved-empty-icon">
                <Bookmark size={22} />
              </div>
              <h3>
                {search
                  ? 'No matching researchers.'
                  : missing.some((id) => ids.includes(id))
                    ? 'Researchers could not be loaded.'
                    : tab === 'shortlist'
                      ? 'Your shortlist starts here.'
                      : 'No rejected researchers.'}
              </h3>
              <p>
                {search
                  ? 'Try searching for another name.'
                  : missing.some((id) => ids.includes(id))
                    ? 'Your decisions are still saved. Retry loading the profiles.'
                    : tab === 'shortlist'
                      ? 'Save researchers from your search results to find them here.'
                      : 'Researchers you reject will appear here, ready to restore.'}
              </p>
              {tab === 'shortlist' && !search && (
                <Link href="/#search" className="saved-inline-link">
                  Explore researchers <ArrowUpRight size={16} />
                </Link>
              )}
            </div>
          ) : (
            <>
              <p className="saved-compare-hint">
                Select two researchers to compare their work.
              </p>
              <div className="saved-list">
                {rows.map((p) => (
                  <article className="saved-card" key={p.person_id}>
                    <input
                      aria-label={`Select ${p.name} to compare`}
                      type="checkbox"
                      checked={selected.includes(p.person_id)}
                      onChange={(e) =>
                        setSelected((xs) =>
                          e.target.checked
                            ? [...xs, p.person_id].slice(-2)
                            : xs.filter((id) => id !== p.person_id),
                        )
                      }
                    />
                    <div className="avatar">
                      {p.name
                        .split(' ')
                        .slice(0, 2)
                        .map((x) => x[0])
                        .join('')
                        .toUpperCase()}
                    </div>
                    <div className="saved-person">
                      <Link href={`/experts/${p.person_id}`}>{p.name}</Link>
                      <span>
                        {p.topics
                          .slice(0, 3)
                          .map((t) => t.topic)
                          .join(' · ') || 'Research topics unavailable'}
                      </span>
                      <small>
                        {p.publications.length} sourced publications
                      </small>
                    </div>
                    <span className={`decision-badge ${tab}`}>
                      {tab === 'shortlist' ? 'SHORTLISTED' : 'REJECTED'}
                    </span>
                    <div className="saved-actions">
                      <Link
                        href={`/experts/${p.person_id}`}
                        className="text-link"
                      >
                        View profile ↗
                      </Link>
                      {tab === 'shortlist' ? (
                        <>
                          <button
                            disabled={busy}
                            onClick={() => decision(p.person_id, 'reject')}
                          >
                            Reject
                          </button>
                          <button
                            className="outline-button"
                            disabled={busy}
                            onClick={() => decision(p.person_id, 'clear')}
                          >
                            Remove
                          </button>
                        </>
                      ) : (
                        <button
                          className="outline-button"
                          disabled={busy}
                          onClick={() => decision(p.person_id, 'clear')}
                        >
                          Restore
                        </button>
                      )}
                    </div>
                  </article>
                ))}
              </div>
              {comparisons.length === 2 && (
                <button
                  className="saved-compare-button"
                  onClick={() =>
                    document
                      .getElementById('expert-comparison')
                      ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                  }
                >
                  Compare selected experts <ArrowUpRight size={16} />
                </button>
              )}
              {comparisons.length === 2 && (
                <section id="expert-comparison" className="comparison">
                  <div className="section-title">
                    <div>
                      <span className="eyebrow">SIDE BY SIDE</span>
                      <h2>Compare experts</h2>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => setSelected([])}
                    >
                      Close
                    </button>
                  </div>
                  <div className="compare-grid">
                    {comparisons.map((p) => (
                      <div key={p.person_id}>
                        <h3>
                          <Link href={`/experts/${p.person_id}`}>{p.name}</Link>
                        </h3>
                        <p>
                          {p.publications.length} publications in this graph
                        </p>
                        <strong>Topics</strong>
                        <ul>
                          {p.topics.slice(0, 8).map((t) => (
                            <li key={t.topic}>{t.topic}</li>
                          ))}
                        </ul>
                        <strong>Recent evidence</strong>
                        <ul>
                          {[...p.publications]
                            .sort((a, b) => (b.year || 0) - (a.year || 0))
                            .slice(0, 3)
                            .map((pub) => (
                              <li key={pub.paper_id}>
                                {pub.title} ({pub.year || 'N.D.'})
                              </li>
                            ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </section>
        <section
          className="saved-memory"
          id="session-settings"
          aria-labelledby="memory-heading"
        >
          <div className="saved-section-heading">
            <div>
              <span className="eyebrow">SESSION & PRIVACY</span>
              <h2 id="memory-heading">Your session memory</h2>
              <p>
                Your shortlist, rejected researchers and last search help the
                assistant understand follow-up requests.
              </p>
            </div>
            <ShieldCheck size={24} aria-hidden="true" />
          </div>
          <div className="saved-memory-details">
            <div>
              <span>LAST RESEARCH QUERY</span>
              <p>{memory?.last_query || 'No query stored yet.'}</p>
            </div>
            <div>
              <span>SAVED SHORTLIST IDS</span>
              <p>{memory?.shortlisted_person_ids.join(', ') || 'None'}</p>
            </div>
            <div>
              <span>REJECTED IDS</span>
              <p>{memory?.rejected_person_ids.join(', ') || 'None'}</p>
            </div>
          </div>
          <div className="saved-memory-delete">
            <div>
              <h3>Delete session memory</h3>
              <p>
                Remove this search session, including its saved decisions and
                search context. Independent conversations are managed
                separately.
              </p>
            </div>
            <button
              type="button"
              disabled={busy || !session}
              onClick={deleteSession}
            >
              <Trash2 size={16} /> {busy ? 'Deleting…' : 'Delete session'}
            </button>
          </div>
        </section>
      </main>
    </AppLayout>
  );
}
