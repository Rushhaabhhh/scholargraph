'use client';
import { FormEvent, Fragment, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import type { ChatResponse, Expert, Memory } from '../lib/types';
import { Icon } from './Icon';
import { VoiceConsole } from './VoiceConsole';

export type ChatTurn = {
  role: 'user' | 'assistant';
  text: string;
  response?: ChatResponse;
};
const toolLabels: Record<string, string> = {
  search_experts: 'Search researchers',
  get_profile: 'Retrieve researcher profile',
  find_collaboration_path: 'Trace collaboration path',
};

export function AssistantDialog({
  open,
  onClose,
  online,
  session,
  memory,
  results,
  turns,
  message,
  busy,
  searching,
  error,
  onMessageChange,
  onSend,
  onVoiceSend,
  onClearMemory,
  onViewResults,
}: {
  open: boolean;
  onClose: () => void;
  online: boolean;
  session: string;
  memory: Memory | null;
  results: Expert[];
  turns: ChatTurn[];
  message: string;
  busy: boolean;
  searching: boolean;
  error: string;
  onMessageChange: (value: string) => void;
  onSend: (event: FormEvent) => void;
  onVoiceSend: (text: string, signal?: AbortSignal) => Promise<string>;
  onClearMemory: () => void;
  onViewResults: () => void;
}) {
  const [mode, setMode] = useState<'text' | 'voice'>('text');
  const closeRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const wasOpen = useRef(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!open) {
      if (wasOpen.current) returnFocus.current?.focus();
      wasOpen.current = false;
      return;
    }
    if (!wasOpen.current && document.activeElement instanceof HTMLElement)
      returnFocus.current = document.activeElement;
    wasOpen.current = true;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key === 'Tab') {
        const dialog = document.querySelector<HTMLElement>('.assistant-dialog');
        const controls = dialog
          ? Array.from(
              dialog.querySelectorAll<HTMLElement>(
                'button:not([disabled]),a[href],textarea,[tabindex]:not([tabindex="-1"])',
              ),
            )
          : [];
        const first = controls[0],
          last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  const label = (id: number) =>
    results.find((person) => person.person_id === id)?.name ||
    `Researcher #${id}`;
  const suggestions = [
    'Search for graph retrieval',
    ...(memory?.last_result_ids.length ? ['Show profile #1'] : []),
    ...(memory && memory.last_result_ids.length >= 2
      ? ['Find collaboration path between #1 and #2']
      : []),
    ...(memory?.last_query ? ['Show recent results'] : []),
    'Show my shortlist',
  ];
  return (
    <>
      <button
        className="assistant-scrim"
        aria-label="Close assistant"
        onClick={onClose}
      />
      <aside
        className="assistant-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Research assistant"
      >
        <div className="assistant-header">
          <div className="assistant-avatar">
            <Icon name="spark" size={20} />
          </div>
          <div>
            <h2>Research assistant</h2>
            <p>
              <i className={online ? '' : 'is-offline'} />
              {online
                ? 'CONNECTED TO THE RESEARCH GRAPH'
                : 'BACKEND UNAVAILABLE'}
            </p>
          </div>
          <button
            ref={closeRef}
            className="assistant-close"
            aria-label="Close research assistant"
            onClick={onClose}
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <div
          className="assistant-mode-tabs"
          role="tablist"
          aria-label="Assistant mode"
        >
          <button
            role="tab"
            aria-selected={mode === 'text'}
            onClick={() => setMode('text')}
          >
            <Icon name="message" size={15} />
            Text conversation
          </button>
          <button
            role="tab"
            aria-selected={mode === 'voice'}
            onClick={() => setMode('voice')}
          >
            <Icon name="audio" size={16} />
            Voice conversation
          </button>
        </div>
        <div className="assistant-body">
          {mode === 'voice' && (
            <VoiceConsole
              session={session}
              busy={busy || searching}
              onSend={onVoiceSend}
            />
          )}
          <div className="assistant-intro">
            <span className="mini-label">A GRAPH TOOL ASSISTANT</span>
            <h3>
              Search. Inspect.
              <br />
              Follow connections.
            </h3>
            <p>
              Use an explicit search command, or use the commands below to open
              profiles, find paths, and manage your shortlist. For match
              rationale, open “Why this match” on a result. When configured,
              general questions can use AI chat without accessing the graph;
              those answers are not source-verified.
            </p>
          </div>
          <div className="assistant-command-guide">
            <strong>SUPPORTED ACTIONS</strong>
            <span>
              <code>Search for [topic]</code>
              <code>Show profile #1</code>
              <code>Find collaboration path between #1 and #2</code>
              <code>Shortlist #1 · Reject #1</code>
              <code>Show recent results · Show my shortlist</code>
            </span>
          </div>
          <div className="session-memory">
            <div className="memory-heading">
              <span>
                <Icon name="bookmark" size={15} /> SESSION MEMORY
              </span>
              <button
                disabled={!session || busy}
                onClick={() => {
                  if (
                    window.confirm(
                      'Clear this session’s search context and shortlist/reject decisions?',
                    )
                  )
                    onClearMemory();
                }}
              >
                Clear
              </button>
            </div>
            <p>
              {memory?.shortlisted_person_ids.length || 0} shortlisted ·{' '}
              {memory?.rejected_person_ids.length || 0} dismissed
              {memory?.last_query ? ` · Last search: ${memory.last_query}` : ''}
            </p>
          </div>
          <div className="suggestions">
            <span>QUICK ACTIONS</span>
            {suggestions.map((s) => (
              <button
                key={s}
                disabled={busy || searching || !session}
                onClick={() => {
                  onMessageChange(s);
                  inputRef.current?.focus();
                }}
              >
                {s}
                <Icon name="arrow" size={14} />
              </button>
            ))}
          </div>
          <div className="chat-history" aria-live="polite">
            {turns.map((turn, i) => (
              <div key={i} className={`chat-message ${turn.role}`}>
                <span>{turn.role === 'user' ? 'YOU' : 'SCHOLARGRAPH'}</span>
                <p>{turn.text}</p>
                {turn.response && (
                  <div className="assistant-response">
                    <div className="tool-activity">
                      <span className="response-kicker">TOOL ACTIVITY</span>
                      {turn.response.tool_calls.length ? (
                        turn.response.tool_calls.map((call, j) => (
                          <span
                            key={`${call.tool}-${j}`}
                            className={`tool-chip ${call.outcome}`}
                          >
                            <i />
                            {toolLabels[call.tool] || 'Graph tool'} ·{' '}
                            {call.outcome}
                          </span>
                        ))
                      ) : (
                        <span className="tool-chip">
                          <i />
                          {turn.response.message.startsWith('Decision saved')
                            ? 'Session decision saved'
                            : 'No graph tool used for this action'}
                        </span>
                      )}
                    </div>
                    <div className="applied-memory">
                      <span className="response-kicker">
                        MEMORY APPLIED TO THIS TURN
                      </span>
                      <p>
                        {
                          turn.response.memory_applied.shortlisted_person_ids
                            .length
                        }{' '}
                        shortlisted ·{' '}
                        {
                          turn.response.memory_applied.rejected_person_ids
                            .length
                        }{' '}
                        dismissed
                        {turn.response.memory_applied.last_query
                          ? ` · Search context: ${turn.response.memory_applied.last_query}`
                          : ' · No previous search context'}
                      </p>
                    </div>
                    {turn.response.results?.length > 0 && (
                      <button
                        className="assistant-result-link"
                        onClick={onViewResults}
                      >
                        View {turn.response.results.length} ranked researchers{' '}
                        <Icon name="arrow" size={13} />
                      </button>
                    )}
                    {turn.response.profile && (
                      <div className="assistant-result-card">
                        <div>
                          <span className="response-kicker">
                            SOURCE PROFILE
                          </span>
                          <strong>{turn.response.profile.name}</strong>
                          <small>
                            {turn.response.profile.publications.length}{' '}
                            publications · {turn.response.profile.topics.length}{' '}
                            title-derived topics
                          </small>
                        </div>
                        <ul>
                          {turn.response.profile.publications
                            .slice(0, 3)
                            .map((p) => (
                              <li key={p.paper_id}>
                                <span>{p.year || 'Year unknown'}</span>
                                {p.title}
                                <small>DBLP · {p.paper_id}</small>
                              </li>
                            ))}
                        </ul>
                        <Link
                          href={`/experts/${turn.response.profile.person_id}`}
                        >
                          Open full evidence profile{' '}
                          <Icon name="forward" size={13} />
                        </Link>
                      </div>
                    )}
                    {turn.response.profiles?.map((profile) => (
                      <div
                        className="assistant-shortlist-profile"
                        key={profile.person_id}
                      >
                        <Link href={`/experts/${profile.person_id}`}>
                          {profile.name} <Icon name="arrow" size={12} />
                        </Link>
                        <small>
                          {profile.publications.length} source publications
                        </small>
                      </div>
                    ))}
                    {turn.response.path && (
                      <div className="assistant-path">
                        <span className="response-kicker">
                          COLLABORATION PATH ·{' '}
                          {turn.response.path.person_ids.length} PEOPLE
                        </span>
                        <strong>
                          {turn.response.path.person_ids.length
                            ? turn.response.path.person_ids.map((id, index) => (
                                <Fragment key={`${id}-${index}`}>
                                  {index > 0 && (
                                    <Icon name="forward" size={13} />
                                  )}
                                  {label(id)}
                                </Fragment>
                              ))
                            : 'No path found within the traversal limit'}
                        </strong>
                        {turn.response.path.edges.map((edge, j) => (
                          <p key={`${edge.from}-${edge.to}-${j}`}>
                            {label(edge.from)} and {label(edge.to)}
                            {edge.evidence.map((p) => (
                              <small key={p.paper_id}>
                                {p.title} · {p.year || 'date unknown'} · DBLP{' '}
                                {p.paper_id}
                              </small>
                            ))}
                          </p>
                        ))}
                        {turn.response.path.truncated && (
                          <small>
                            Path search reached its traversal limit.
                          </small>
                        )}
                      </div>
                    )}
                    {turn.response.claims.some((claim) => !claim.supported) && (
                      <p className="assistant-caveat">
                        Some claims returned for this turn are unverified. Check
                        the cited evidence before relying on them.
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
            {busy && (
              <div className="chat-message assistant" role="status">
                <span>SCHOLARGRAPH</span>
                <p>
                  <span className="spinner" />
                  Running the requested graph operation…
                </p>
              </div>
            )}
          </div>
        </div>
        {error && (
          <div className="error-banner assistant-error" role="alert">
            {error}
            {message.trim() && (
              <button
                type="button"
                onClick={() => formRef.current?.requestSubmit()}
              >
                Retry
              </button>
            )}
          </div>
        )}
        <form ref={formRef} className="chat-form" onSubmit={onSend}>
          <label className="sr-only" htmlFor="message">
            Message research assistant
          </label>
          <textarea
            ref={inputRef}
            id="message"
            rows={2}
            placeholder="Enter a supported command…"
            value={message}
            maxLength={4000}
            disabled={!session || busy || searching}
            onChange={(e) => onMessageChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (message.trim() && !busy) formRef.current?.requestSubmit();
              }
            }}
          />
          <button
            aria-label="Send message"
            disabled={!session || busy || searching || !message.trim()}
          >
            {busy ? '…' : '↑'}
          </button>
        </form>
        <div className="assistant-footer">
          Responses use the connected DBLP graph and session tools. For general
          conversation, <Link href="/chat">open AI chat</Link>.
        </div>
      </aside>
    </>
  );
}
