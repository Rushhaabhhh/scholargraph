'use client';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AppLayout } from './AppLayout';
import { getSession } from '../lib/session';
import { ExpertCard } from './ExpertCard';
import { EvidenceGraph } from './EvidenceGraph';
import { PipelineStory } from './PipelineStory';
import { ResearchHero } from './ResearchHero';
import { CursorSwarm } from './CursorSwarm';
import { openAssistantForProfile } from '../lib/assistant';
import { Icon } from './Icon';
import {
  ArrowUpRight,
  ArrowRight,
  CalendarDays,
  Compass,
  Network,
  Search,
  Sparkles,
} from 'lucide-react';
import { api, ApiError, json, requestId } from '../lib/api';
import type {
  Expert,
  Memory,
  SearchResponse,
} from '../lib/types';
type Health = {
  status: 'ok' | 'degraded';
  papers: number;
  authors: number;
  model_version: string;
  query_provider: string;
};
const examples = [
  'Graph neural networks',
  'Information retrieval',
  'Computer vision',
];
const prompts = [
  'Researchers working on graph neural networks for drug discovery',
  'Experts in trustworthy machine learning and fairness',
  'Researchers studying information retrieval and language models',
  'Computer vision for medical image analysis',
];

export function Workspace() {
  const [session, setSession] = useState('');
  const [memory, setMemory] = useState<Memory | null>(null);
  const [ready, setReady] = useState(false);
  const [query, setQuery] = useState('');
  const [promptIndex, setPromptIndex] = useState(0);
  const [recency, setRecency] = useState<'auto' | 'any' | 'recent'>('auto');
  const [sinceYear, setSinceYear] = useState('');
  const [health, setHealth] = useState<Health | null>(null);
  const [searched, setSearched] = useState('');
  const [results, setResults] = useState<Expert[]>([]);
  const [searchInfo, setSearchInfo] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (
      query ||
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    )
      return;
    const timer = window.setInterval(
      () => setPromptIndex((index) => (index + 1) % prompts.length),
      3600,
    );
    return () => window.clearInterval(timer);
  }, [query]);
  const searchAbort = useRef<AbortController | null>(null);
  const searchSeq = useRef(0);
  const scrollAfterSearch = useRef(false);
  const apiOnline = health?.status === 'ok';

  useEffect(() => {
    let active = true,
      initialized = false,
      initializing = false;
    async function connect() {
      if (initialized || initializing) return;
      initializing = true;
      try {
        const info = await getSession();
        if (!active) return;
        initialized = true;
        setSession(info.session_id);
        setMemory(info.memory);
        setReady(true);
        setError('');
        const asked = new URLSearchParams(window.location.search).get('ask');
        if (asked && /^\d{1,16}$/.test(asked)) {
          window.location.replace(`/chat?profile=${asked}&name=researcher`);
          return;
        }
        try {
          const cached = JSON.parse(
            sessionStorage.getItem('scholargraph-results') ||
              sessionStorage.getItem('hiresense-results') ||
              'null',
          ) as SearchResponse | null;
          if (cached) {
            setQuery(cached.query);
            setSearched(cached.query);
            setResults(cached.results);
            setSearchInfo(cached);
            const saved = JSON.parse(
              sessionStorage.getItem('scholargraph-filters') || 'null',
            );
            setRecency(
              ['auto', 'any', 'recent'].includes(saved?.recency)
                ? saved.recency
                : 'auto',
            );
            setSinceYear(
              typeof saved?.sinceYear === 'string' ? saved.sinceYear : '',
            );
          }
        } catch {
          sessionStorage.removeItem('scholargraph-results');
          sessionStorage.removeItem('hiresense-results');
        }
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          setReady(true);
        }
      } finally {
        initializing = false;
      }
    }
    const refresh = () => {
      api<Health>('/health')
        .then((value) => {
          if (active) setHealth(value);
        })
        .catch(() => {
          if (active) setHealth(null);
        });
      void connect();
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
      searchAbort.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (searching || !scrollAfterSearch.current) return;
    scrollAfterSearch.current = false;
    const frame = window.requestAnimationFrame(() => {
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      (document.getElementById('ranked-results') || document.getElementById('discovery-results'))?.scrollIntoView({
        behavior: reduced ? 'auto' : 'smooth',
        block: 'start',
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [searching, searchInfo]);

  async function currentMemory() {
    const m = await api<Memory>(`/sessions/${session}/memory`);
    setMemory(m);
    return m;
  }
  async function mutate<T extends { memory: Memory }>(
    path: string,
    method: string,
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<T> {
    const m = await currentMemory();
    const payload = {
      ...body,
      expected_version: m.version,
      request_id: requestId(),
    };
    try {
      return await api<T>(path, json(method, payload, signal));
    } catch (e) {
      if (e instanceof ApiError && e.status === 0)
        return api<T>(path, json(method, payload, signal));
      if (e instanceof ApiError && e.status === 409) {
        await currentMemory();
        throw new Error(
          'Your session changed during this request. Please try again.',
        );
      }
      throw e;
    }
  }
  async function search(
    value: string,
    filters: { recency?: 'auto' | 'any' | 'recent'; sinceYear?: string } = {},
  ) {
    const q = value.trim();
    const appliedRecency = filters.recency ?? recency;
    const appliedYear = filters.sinceYear ?? sinceYear;
    if (
      appliedYear &&
      (!Number.isInteger(Number(appliedYear)) ||
        Number(appliedYear) < 1 ||
        Number(appliedYear) > 9999)
    ) {
      setError('Enter a year from 1 to 9999.');
      return;
    }
    if (!q || !session) return;
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    const seq = ++searchSeq.current;
    setQuery(q);
    setSearching(true);
    setError('');
    try {
      let data: SearchResponse | undefined;
      for (let attempt = 0; attempt < 2; attempt++) {
        const m = await currentMemory();
        if (seq !== searchSeq.current || controller.signal.aborted) return;
        const payload = {
          query: q,
          limit: 10,
          recency_preference: appliedRecency === 'auto' ? null : appliedRecency,
          since_year: appliedYear ? Number(appliedYear) : null,
          session_id: session,
          expected_version: m.version,
          request_id: requestId(),
        };
        try {
          data = await api<SearchResponse>(
            '/search',
            json('POST', payload, controller.signal),
          );
          break;
        } catch (e) {
          if (e instanceof ApiError && e.status === 409 && attempt === 0)
            continue;
          throw e;
        }
      }
      if (!data || seq !== searchSeq.current || controller.signal.aborted)
        return;
      setRecency(appliedRecency);
      setSinceYear(appliedYear);
      setSearched(q);
      setResults(data.results);
      setSearchInfo(data);
      sessionStorage.setItem('scholargraph-results', JSON.stringify(data));
      sessionStorage.setItem(
        'scholargraph-filters',
        JSON.stringify({ recency: appliedRecency, sinceYear: appliedYear }),
      );
      if (data.memory) setMemory(data.memory);
      scrollAfterSearch.current = true;
    } catch (e) {
      if (seq === searchSeq.current && (e as Error).name !== 'AbortError')
        setError(
          e instanceof ApiError && e.status === 409
            ? 'Your session changed while searching. Please search again.'
            : (e as Error).message,
        );
    } finally {
      if (seq === searchSeq.current) setSearching(false);
    }
  }
  async function decide(
    id: number,
    decision: 'shortlist' | 'reject' | 'clear',
  ) {
    if (!session) return;
    setBusy(true);
    setError('');
    try {
      const data = await mutate<{ memory: Memory }>(
        `/sessions/${session}/decisions/${id}`,
        'PUT',
        { decision },
      );
      setMemory(data.memory);
    } catch (e) {
      await currentMemory().catch(() => {});
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const visible = useMemo(
    () =>
      results.filter((r) => !memory?.rejected_person_ids.includes(r.person_id)),
    [results, memory?.rejected_person_ids],
  );
  const filtersValid =
    !sinceYear ||
    (Number.isInteger(Number(sinceYear)) &&
      Number(sinceYear) >= 1 &&
      Number(sinceYear) <= 9999);
  return (
    <AppLayout>
      <div className="home-page" id="top">
        <ResearchHero health={health} />
        <PipelineStory />
        <section
          className="search-section"
          id="search"
          aria-labelledby="search-title"
        >
          <div className="search-heading">
            <div>
              <div className="section-kicker">
                <span className="kicker-mark">
                  <Icon name="search" size={15} />
                </span>{' '}
                03 / START YOUR DISCOVERY <span className="kicker-line" />
              </div>
              <h2 id="search-title">
                What expertise are you <em>looking for?</em>
              </h2>
              <p>
                Describe the problem, method, or field. We’ll search the graph
                and show the publication trail.
              </p>
            </div>
            <span
              className={`backend-pill ${apiOnline ? 'is-online' : 'is-offline'}`}
            >
              <i />
              {apiOnline ? 'BACKEND READY' : 'BACKEND UNAVAILABLE'}
            </span>
          </div>
          <form
            className={`search-composer ${searching ? 'is-searching' : ''}`}
            onSubmit={(e) => {
              e.preventDefault();
              search(query);
            }}
          >
            <div className="discovery-form-heading">
              <div>
                <span className="discovery-form-icon">
                  <Sparkles size={19} />
                </span>
                <div>
                  <label htmlFor="query">RESEARCH QUESTION OR TOPIC</label>
                  <p>Describe the expertise you need in your own words.</p>
                </div>
              </div>
              <span>YOUR STARTING POINT</span>
            </div>
            <div className="search-input-row">
              <span className="composer-icon">
                <Icon name="search" size={21} />
              </span>
              <input
                id="query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={prompts[promptIndex]}
                maxLength={4000}
              />
              {query && (
                <button
                  type="button"
                  className="clear-query"
                  aria-label="Clear query"
                  onClick={() => setQuery('')}
                >
                  <Icon name="close" size={16} />
                </button>
              )}
              <button
                className="search-submit"
                disabled={
                  !ready || !session || busy || !query.trim() || !filtersValid
                }
              >
                {searching ? (
                  <>
                    <span className="button-spinner" />
                    Searching
                  </>
                ) : (
                  <>
                    Find researchers <ArrowUpRight size={19} />
                  </>
                )}
              </button>
            </div>
            <div className="filter-row">
              <div className="filter-group">
                <div className="filter-fields">
                  <label>
                    <span>
                      <CalendarDays size={15} /> PUBLICATION ACTIVITY
                    </span>
                    <select
                      aria-label="Publication activity"
                      value={recency}
                      onChange={(e) =>
                        setRecency(e.target.value as 'auto' | 'any' | 'recent')
                      }
                    >
                      <option value="auto">Use query dates</option>
                      <option value="any">Any time</option>
                      <option value="recent">Recent work</option>
                    </select>
                  </label>
                  <label>
                    <span>FROM YEAR</span>
                    <input
                      aria-label="Since year"
                      type="number"
                      min="1"
                      max="9999"
                      placeholder="Any year"
                      value={sinceYear}
                      onChange={(e) => setSinceYear(e.target.value.slice(0, 4))}
                    />
                  </label>
                  {sinceYear && !filtersValid && (
                    <span className="filter-error" role="alert">
                      Enter a year from 1 to 9999.
                    </span>
                  )}
                  {(recency !== 'auto' || sinceYear) && (
                    <button
                      className="clear-filters"
                      type="button"
                      onClick={() => {
                        setRecency('auto');
                        setSinceYear('');
                        if (query.trim() && session)
                          search(query, { recency: 'auto', sinceYear: '' });
                      }}
                    >
                      Reset filters
                    </button>
                  )}
                </div>
              </div>
              <div className="query-examples">
                <span>EXPLORE AN EXAMPLE</span>
                {examples.map((x) => (
                  <button
                    type="button"
                    key={x}
                    disabled={!session || busy}
                    onClick={() => {
                      setQuery(x);
                      search(x);
                    }}
                  >
                    {x} <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
            </div>
          </form>
          {error && (
            <div className="error-banner" role="alert">
              {error}{' '}
              {session ? (
                <button onClick={() => search(query)}>Retry search</button>
              ) : (
                <button onClick={() => window.location.reload()}>
                  Retry connection
                </button>
              )}
            </div>
          )}
          <div className="results-heading" id="discovery-results">
            <div>
              <span className="eyebrow">EVIDENCE-LED DISCOVERY</span>
              <h3>
                {searched
                  ? 'Researchers for your question'
                  : 'Your results will appear here'}
                {searched && (
                  <span className="count">
                    {String(visible.length).padStart(2, '0')}
                  </span>
                )}
              </h3>
            </div>
            {searched && searchInfo && (
              <div className="results-meta">
                <span>
                  {searchInfo.understanding.intent.topics.join(' · ') ||
                    searchInfo.query}
                </span>
                <small>
                  GRAPH CUTOFF {searchInfo.effective_filters.graph_cutoff_year}{' '}
                  ·{' '}
                  {searchInfo.understanding.provider
                    .replace('_', ' ')
                    .toUpperCase()}
                </small>
              </div>
            )}
          </div>
          {searched && searchInfo && (
            <div className="search-summary">
              <span>QUERY</span>
              <b>{searchInfo.query}</b>
              <i />
              <span>SEARCH INTENT</span>
              <b>
                {searchInfo.understanding.intent.topics.join(' · ') ||
                  'No separate topic extraction'}
              </b>
              {searchInfo.effective_filters.since_year && (
                <em>Since {searchInfo.effective_filters.since_year}</em>
              )}
              {searchInfo.understanding.intent.recency_preference ===
                'recent' && <em>Recent work</em>}
            </div>
          )}
          {searching ? (
            <div
              className="skeleton-list"
              role="status"
              aria-label="Searching the research graph"
            >
              <div />
              <div />
              <div />
            </div>
          ) : !searched ? (
            <div className="results-placeholder">
              <div className="discovery-empty-art" aria-hidden="true">
                <span className="empty-orbit one" />
                <span className="empty-orbit two" />
                <span className="empty-orbit three" />
                <span className="empty-art-center">
                  <Network size={27} />
                </span>
                <i />
                <b />
                <em />
              </div>
              <div className="discovery-empty-copy">
                <span className="discovery-empty-label">
                  <Compass size={15} /> THE NEXT DISCOVERY STARTS HERE
                </span>
                <strong>One thoughtful query can open a whole field.</strong>
                <p>
                  Start with a research challenge. Your results will include
                  people, the work they published, and the connections behind
                  the ranking.
                </p>
                <span className="discovery-empty-note">
                  <Search size={15} /> Search above to explore the research
                  graph
                </span>
              </div>
            </div>
          ) : visible.length === 0 ? (
            <div className="state">
              <h3>No researchers found for this view.</h3>
              <p>
                No supported title matches were found, or the filters exclude
                the available evidence. Try alternative research terms, change
                the year filter, or restore a rejected researcher. Searches with
                no shared title terms can miss relevant synonyms.
              </p>
              <a className="text-link" href="/shortlist">
                Review shortlist and rejected people{' '}
                <ArrowRight size={14} aria-hidden="true" />
              </a>
            </div>
          ) : (
            <>
              <div className="graph-intro"><Network size={20} /><div><strong>Explore the evidence graph</strong><p>Select a researcher or paper to explore their connections.</p></div></div>
              <EvidenceGraph experts={visible} />
              <div className="result-list" id="ranked-results">
                {visible.map((expert) => (
                  <ExpertCard
                    key={expert.person_id}
                    expert={expert}
                    index={results.findIndex(
                      (result) => result.person_id === expert.person_id,
                    )}
                    memory={memory}
                    busy={busy || searching}
                    onDecision={decide}
                    onAsk={(expert) => {
                      openAssistantForProfile({ id: expert.person_id, name: expert.name });
                    }}
                  />
                ))}
              </div>
              <p className="results-footnote">
                Scores order retrieved matches; they are model ranking scores,
                not probabilities or hiring accuracy. Inspect the sourced
                evidence before making a decision.
              </p>
            </>
          )}
        </section>
      </div>
      <CursorSwarm />
    </AppLayout>
  );
}
