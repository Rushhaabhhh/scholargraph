'use client';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { AppLayout } from './AppLayout';
import { VoiceConsole } from './VoiceConsole';
import Link from 'next/link';
import {
  ArrowLeft,
  ArrowUp,
  AudioLines,
  ChevronDown,
  History,
  MessageSquareText,
  Plus,
  Search,
  Sparkles,
  Square,
} from 'lucide-react';
import { api, ApiError } from '../lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github-dark.css';
import './conversation.css';

type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  preview?: string | null;
};
type Message = {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  rating?: 'helpful' | 'unhelpful' | null;
};
type Document = { id: string; name: string };
type Status = {
  provider: string;
  model: string;
  available: boolean;
  busy?: boolean;
  message: string;
};
const CHAT_SESSION_KEY = 'scholargraph-conversation-session';
const CHAT_ACTIVE_KEY = 'scholargraph-conversation';

let pendingSession: Promise<string> | null = null;
function conversationSession() {
  if (!pendingSession)
    pendingSession = loadConversationSession().finally(() => {
      pendingSession = null;
    });
  return pendingSession;
}
async function loadConversationSession() {
  const saved = localStorage.getItem(CHAT_SESSION_KEY);
  if (saved) {
    try {
      await api(`/sessions/${saved}/memory`);
      return saved;
    } catch (error) {
      if (
        !(error instanceof ApiError) ||
        (error.status !== 404 && error.code !== 'session_graph_mismatch')
      )
        throw error;
      localStorage.removeItem(CHAT_SESSION_KEY);
      localStorage.removeItem(CHAT_ACTIVE_KEY);
    }
  }
  const info = await api<{ session_id: string }>('/sessions', {
    method: 'POST',
  });
  localStorage.setItem(CHAT_SESSION_KEY, info.session_id);
  return info.session_id;
}

export function ConversationWorkspace() {
  return (
    <AppLayout>
      <ConversationContent />
    </AppLayout>
  );
}

export function ConversationContent({
  floating = false,
  visible = true,
  onState,
  onClose,
}: {
  floating?: boolean;
  visible?: boolean;
  onState?: (state: string) => void;
  onClose?: () => void;
}) {
  const [session, setSession] = useState(''),
    [items, setItems] = useState<Conversation[]>([]),
    [active, setActive] = useState(''),
    [messages, setMessages] = useState<Message[]>([]),
    [documents, setDocuments] = useState<Document[]>([]),
    [profile, setProfile] = useState<{ id: number; name: string } | null>(null),
    [input, setInput] = useState(''),
    [busy, setBusy] = useState(false),
    [research, setResearch] = useState(false),
    [progress, setProgress] = useState(''),
    [mode, setMode] = useState<'text' | 'voice'>('text'),
    [error, setError] = useState(''),
    [status, setStatus] = useState<Status | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false),
    [historySearch, setHistorySearch] = useState(''),
    [voicePhase, setVoicePhase] = useState('idle');
  const abort = useRef<AbortController | null>(null),
    stopGeneration = useRef<(() => void) | null>(null),
    activeRef = useRef(''),
    tail = useRef<HTMLDivElement>(null);
  activeRef.current = active;
  const headers = useCallback((id: string) => ({ 'X-Session-ID': id }), []);
  const refresh = useCallback(
    async (id: string) => {
      const list = await api<Conversation[]>('/conversations', {
        headers: headers(id),
      });
      setItems(list);
      return list;
    },
    [headers],
  );
  const select = useCallback(
    async (id: string, sid: string) => {
      const value = await api<
        Conversation & { messages: Message[]; documents: Document[] }
      >(`/conversations/${id}`, { headers: headers(sid) });
      activeRef.current = id;
      setActive(id);
      setMessages(value.messages);
      setDocuments(value.documents);
      localStorage.setItem(CHAT_ACTIVE_KEY, id);
      setError('');
    },
    [headers],
  );
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = Number(params.get('profile'));
    const name = params.get('name');
    if (Number.isSafeInteger(id) && id > 0 && name) {
      setInput(`What can you tell me about ${name}'s research?`);
      setProfile({ id, name });
      localStorage.removeItem(CHAT_ACTIVE_KEY);
      window.history.replaceState({}, '', '/chat');
    }
  }, []);
  useEffect(() => {
    let live = true;
    conversationSession()
      .then(async (sid) => {
        if (!live) return;
        setSession(sid);
        const [list, provider] = await Promise.all([
          refresh(sid),
          api<Status>('/conversations/status'),
        ]);
        if (!live) return;
        setStatus(provider);
        const prior = localStorage.getItem(CHAT_ACTIVE_KEY);
        if (prior && list.some((x) => x.id === prior)) await select(prior, sid);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
      abort.current?.abort();
    };
  }, [refresh, select]);
  useEffect(() => {
    if (!session || status?.provider !== 'local') return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      api<Status>('/conversations/status', { signal: controller.signal })
        .then(setStatus)
        .catch(() => {});
    }, 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [session, status?.provider]);
  useEffect(() => {
    if (visible && mode === 'text')
      tail.current?.scrollIntoView({ block: 'nearest' });
  }, [messages, visible, mode]);
  useEffect(() => {
    const last = messages.at(-1);
    onState?.(
      busy
        ? last?.role === 'assistant' && last.content
          ? 'responding'
          : 'processing'
        : mode === 'voice' && visible
          ? voicePhase === 'listening' || voicePhase === 'starting'
            ? 'listening'
            : voicePhase === 'speaking'
              ? 'responding'
              : voicePhase === 'processing' || voicePhase === 'transcribing'
                ? 'processing'
                : 'idle'
          : 'idle',
    );
  }, [busy, messages, mode, voicePhase, visible, onState]);
  async function create() {
    if (!session || busy) return '';
    setBusy(true);
    try {
      const item = await api<Conversation>('/conversations', {
        method: 'POST',
        headers: headers(session),
      });
      await refresh(session);
      await select(item.id, session);
      return item.id;
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (!session || busy) return;
    await api(`/conversations/${id}`, {
      method: 'DELETE',
      headers: headers(session),
    });
    if (activeRef.current === id) {
      setActive('');
      activeRef.current = '';
      setMessages([]);
      setDocuments([]);
      localStorage.removeItem(CHAT_ACTIVE_KEY);
    }
    await refresh(session);
  }
  async function rename(item: Conversation) {
    const text = window.prompt('Rename conversation', item.title)?.trim();
    if (!text || text === item.title) return;
    await api(`/conversations/${item.id}`, {
      method: 'PATCH',
      headers: headers(session),
      body: JSON.stringify({ text }),
    });
    await refresh(session);
  }
  async function send(value: string, external?: AbortSignal, editId?: number) {
    const text = value.trim();
    if (!text || !session || busy)
      throw new Error('Wait for the current response to finish.');
    setError('');
    setBusy(true);
    let id = activeRef.current;
    const controller = new AbortController();
    abort.current = controller;
    let stopping = false,
      requestStarted = false;
    const onAbort = () => {
      stopping = true;
      setProgress('Stopping generation…');
      if (id && requestStarted) {
        void api(`/conversations/${id}/stop`, {
          method: 'POST',
          headers: headers(session),
        }).catch(() => controller.abort());
      }
    };
    stopGeneration.current = onAbort;
    external?.addEventListener('abort', onAbort, { once: true });
    if (external?.aborted) onAbort();
    let answer = '';
    try {
      if (!id) {
        const item = await api<Conversation>('/conversations', {
          method: 'POST',
          headers: headers(session),
        });
        id = item.id;
        activeRef.current = id;
        setActive(id);
        localStorage.setItem(CHAT_ACTIVE_KEY, id);
      }
      setInput('');
      setMessages((old) => [
        ...(editId
          ? old.slice(
              0,
              old.findIndex((m) => m.id === editId),
            )
          : old),
        { id: Date.now(), role: 'user', content: text },
        { id: Date.now() + 1, role: 'assistant', content: '' },
      ]);
      let response: Response | undefined;
      for (let attempt = 0; attempt < 40; attempt++) {
        response = await fetch(`/api/conversations/${id}/messages`, {
          method: 'POST',
          headers: { ...headers(session), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text,
            research,
            profile_id: profile?.id || null,
            edit_message_id: editId || null,
          }),
          signal: controller.signal,
        });
        if (response.status !== 409) break;
        setProgress('Waiting for the previous response to stop…');
        await new Promise<void>((resolve, reject) => {
          if (controller.signal.aborted) {
            reject(new DOMException('Stopped', 'AbortError'));
            return;
          }
          const cancel = () => {
            clearTimeout(timer);
            reject(new DOMException('Stopped', 'AbortError'));
          };
          const timer = setTimeout(() => {
            controller.signal.removeEventListener('abort', cancel);
            resolve();
          }, 250);
          controller.signal.addEventListener('abort', cancel, { once: true });
        });
      }
      if (!response) throw new Error('Could not start the response.');
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.message || 'Could not start the response.');
      }
      requestStarted = true;
      if (stopping)
        await api(`/conversations/${id}/stop`, {
          method: 'POST',
          headers: headers(session),
        });
      if (!response.body)
        throw new Error('Streaming is unavailable in this browser.');
      const reader = response.body.getReader(),
        decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line) continue;
          const event = JSON.parse(line);
          if (event.type === 'error') throw new Error(event.message);
          if (event.type === 'status')
            setProgress(
              event.status === 'research'
                ? 'Searching research records…'
                : event.status === 'summarizing'
                  ? 'Summarizing earlier conversation…'
                  : 'Generating response…',
            );
          if (event.type === 'delta') {
            answer += event.text;
            setMessages((old) => {
              const copy = [...old];
              const last = copy[copy.length - 1];
              if (last?.role === 'assistant')
                copy[copy.length - 1] = { ...last, content: answer };
              return copy;
            });
          }
        }
        if (done) break;
      }
      if (stopping) throw new DOMException('Stopped', 'AbortError');
      if (!answer) throw new Error('The model returned an empty response.');
      await refresh(session);
      return answer;
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message);
      throw e;
    } finally {
      external?.removeEventListener('abort', onAbort);
      abort.current = null;
      stopGeneration.current = null;
      if (id && controller.signal.aborted) {
        setProgress('Stopping generation…');
        await api(`/conversations/${id}/stop`, {
          method: 'POST',
          headers: headers(session),
        }).catch(() => {});
      }
      if (id) {
        await api<Conversation & { messages: Message[] }>(
          `/conversations/${id}`,
          { headers: headers(session) },
        )
          .then((value) => {
            if (activeRef.current === id) setMessages(value.messages);
          })
          .catch(() => {});
        await refresh(session).catch(() => {});
      }
      setBusy(false);
      setProgress('');
    }
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    void send(input).catch(() => {});
  }
  return (
    <main
      className={`conversation-workspace ${floating ? 'conversation-floating' : ''}`}
    >
      <aside className="conversation-list">
        <Link className="conversation-home" href="/">
          <ArrowLeft size={15} /> Back to home
        </Link>
        <div className="conversation-list-head">
          <span>YOUR CONVERSATIONS</span>
          <button
            type="button"
            onClick={() => {
              setProfile(null);
              void create().catch((e) => setError(e.message));
            }}
            disabled={!session || busy}
          >
            + New
          </button>
        </div>
        <div className="conversation-list-items">
          {items.length === 0 && <p>Your conversations will appear here.</p>}
          {items.map((item) => (
            <div
              className={`conversation-row ${active === item.id ? 'active' : ''}`}
              key={item.id}
            >
              <button
                className="conversation-select"
                onClick={() => {
                  setProfile(null);
                  void select(item.id, session).catch((e) =>
                    setError(e.message),
                  );
                }}
                disabled={busy}
              >
                {item.title}
              </button>
              <button
                aria-label={`Rename ${item.title}`}
                onClick={() =>
                  void rename(item).catch((e) => setError(e.message))
                }
                disabled={busy}
              >
                ✎
              </button>
              <button
                aria-label={`Delete ${item.title}`}
                onClick={() => {
                  if (
                    window.confirm('Delete this conversation and its messages?')
                  )
                    void remove(item.id).catch((e) => setError(e.message));
                }}
                disabled={busy}
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <div className="conversation-model">
          <span className={status?.available ? 'available' : ''} />
          {status
            ? `${status.provider} · ${status.model}`
            : 'Connecting to model'}
          <small>{status?.message}</small>
        </div>
      </aside>
      <section className="conversation-main" aria-label="Conversation">
        <header className="conversation-header">
          <div>
            <span className="conversation-kicker">
              <i /> Scholar AI assistant
            </span>
            <h1>
              {floating
                ? 'AI Assistant'
                : items.find((x) => x.id === active)?.title ||
                  'A space to think.'}
            </h1>
          </div>
          {floating && (
            <div className="floating-header-actions">
              <button
                type="button"
                aria-label="New conversation"
                title="New conversation"
                disabled={!session || busy}
                onClick={() => {
                  setProfile(null);
                  setHistoryOpen(false);
                  void create().catch((e) => setError(e.message));
                }}
              >
                <Plus size={18} />
              </button>
              <button
                type="button"
                aria-label="Saved conversations"
                title="Saved conversations"
                aria-pressed={historyOpen}
                onClick={() => setHistoryOpen((v) => !v)}
              >
                <History size={18} />
              </button>
              <button
                className="assistant-header-close"
                type="button"
                aria-label="Collapse AI assistant"
                title="Close assistant"
                onClick={onClose}
              >
                <ChevronDown size={19} />
              </button>
            </div>
          )}
          <div className="conversation-modes">
            <button
              type="button"
              aria-pressed={mode === 'text'}
              onClick={() => setMode('text')}
            >
              <MessageSquareText size={15} /> Text
            </button>
            <button
              type="button"
              aria-pressed={mode === 'voice'}
              onClick={() => setMode('voice')}
            >
              <AudioLines size={16} /> Voice
            </button>
          </div>
        </header>
        {floating && historyOpen ? (
          <div className="floating-history">
            <div className="floating-history-title">
              <button type="button" onClick={() => setHistoryOpen(false)}>
                <ArrowLeft size={15} /> Back to chat
              </button>
              <div>
                <span>YOUR CONVERSATIONS</span>
                <h2>Saved conversations</h2>
              </div>
              <p>
                Your ideas have a place here. Pick up a conversation whenever
                you are ready.
              </p>
            </div>
            <label className="floating-history-search">
              <Search size={17} />
              <span className="sr-only">Search conversations</span>
              <input
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                placeholder="Search conversations"
              />
            </label>
            <div className="floating-history-list">
              {items.filter((item) =>
                (item.title + ' ' + (item.preview || ''))
                  .toLowerCase()
                  .includes(historySearch.toLowerCase()),
              ).length === 0 && (
                <p className="floating-history-empty">
                  {items.length
                    ? 'No conversations match your search.'
                    : 'Your conversations will appear here.'}
                </p>
              )}
              {Object.entries(
                items
                  .filter((item) =>
                    (item.title + ' ' + (item.preview || ''))
                      .toLowerCase()
                      .includes(historySearch.toLowerCase()),
                  )
                  .reduce<Record<string, Conversation[]>>((groups, item) => {
                    const date = new Date(
                      item.updated_at.replace(' ', 'T') +
                        (item.updated_at.includes('T') ? '' : 'Z'),
                    );
                    const today = new Date();
                    const same = date.toDateString() === today.toDateString();
                    const yesterday = new Date(today);
                    yesterday.setDate(today.getDate() - 1);
                    const label = same
                      ? 'Today'
                      : date.toDateString() === yesterday.toDateString()
                        ? 'Yesterday'
                        : Number.isNaN(date.getTime())
                          ? 'Earlier'
                          : date.toLocaleDateString(undefined, {
                              month: 'long',
                              year: 'numeric',
                            });
                    (groups[label] ??= []).push(item);
                    return groups;
                  }, {}),
              ).map(([label, group]) => (
                <section key={label} className="floating-history-group">
                  <h3>{label}</h3>
                  {group.map((item) => (
                    <article key={item.id} className="floating-history-card">
                      <button
                        className="floating-history-open"
                        disabled={busy}
                        onClick={() => {
                          setProfile(null);
                          void select(item.id, session)
                            .then(() => setHistoryOpen(false))
                            .catch((e) => setError(e.message));
                        }}
                      >
                        <span>{item.title}</span>
                        <small>{item.preview || 'No messages yet'}</small>
                        <time>
                          {(() => {
                            const d = new Date(
                              item.updated_at.replace(' ', 'T') +
                                (item.updated_at.includes('T') ? '' : 'Z'),
                            );
                            return Number.isNaN(d.getTime())
                              ? ''
                              : d.toLocaleString(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  hour: 'numeric',
                                  minute: '2-digit',
                                });
                          })()}
                        </time>
                      </button>
                      <div>
                        <button
                          type="button"
                          aria-label={`Rename ${item.title}`}
                          disabled={busy}
                          onClick={() =>
                            void rename(item).catch((e) => setError(e.message))
                          }
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          aria-label={`Delete ${item.title}`}
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                'Delete this conversation and its messages?',
                              )
                            )
                              void remove(item.id).catch((e) =>
                                setError(e.message),
                              );
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </article>
                  ))}
                </section>
              ))}
            </div>
            {error && (
              <p role="alert" className="floating-history-error">
                {error}
              </p>
            )}
          </div>
        ) : (
          <>
            <div className="conversation-scroll">
              {mode === 'voice' && visible && (
                <VoiceConsole
                  session={session}
                  busy={busy}
                  onSend={send}
                  onPhase={setVoicePhase}
                  latestReply={
                    [...messages]
                      .reverse()
                      .find(
                        (message) =>
                          message.role === 'assistant' && message.content,
                      )?.content || ''
                  }
                />
              )}
              <div className="conversation-timeline">
                {messages.length === 0 && (
                  <div className="conversation-welcome">
                    <div className="conversation-welcome-mark">
                      <Sparkles size={23} />
                    </div>
                    <span>YOUR SPACE TO THINK</span>
                    <h2>
                      Good questions
                      <br />
                      <em>lead somewhere.</em>
                    </h2>
                    <p>
                      Explore a research idea, make sense of a paper, or find
                      the next question worth asking.
                    </p>
                    <small>Thoughtful answers start with your curiosity.</small>
                  </div>
                )}
                {messages.map((m, i) => (
                  <article
                    key={`${m.id}-${i}`}
                    className={`conversation-message ${m.role}`}
                  >
                    <div className="conversation-message-label">
                      {m.role === 'user' ? 'YOU' : 'SCHOLARGRAPH'}
                    </div>
                    <div className="conversation-message-content">
                      {m.content ? (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkMath]}
                          rehypePlugins={[rehypeKatex, rehypeHighlight]}
                          components={{
                            pre: ({ children }) => (
                              <div className="conversation-code">
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    const code =
                                      e.currentTarget.parentElement?.querySelector(
                                        'code',
                                      )?.textContent || '';
                                    void navigator.clipboard
                                      .writeText(code)
                                      .catch(() =>
                                        setError('Could not copy the code.'),
                                      );
                                  }}
                                >
                                  Copy code
                                </button>
                                <pre>{children}</pre>
                              </div>
                            ),
                            a: ({ children, href }) => (
                              <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {children}
                              </a>
                            ),
                          }}
                        >
                          {m.content}
                        </ReactMarkdown>
                      ) : busy ? (
                        'Generating…'
                      ) : (
                        'No response generated.'
                      )}
                    </div>
                    {m.content && (
                      <div className="conversation-message-actions">
                        <button
                          className="message-copy"
                          type="button"
                          onClick={() =>
                            void navigator.clipboard
                              .writeText(m.content)
                              .catch(() =>
                                setError('Could not copy the message.'),
                              )
                          }
                        >
                          Copy
                        </button>
                        {m.role === 'user' && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => {
                              const text = window
                                .prompt(
                                  'Edit your message. Later messages will be replaced.',
                                  m.content,
                                )
                                ?.trim();
                              if (
                                text &&
                                window.confirm(
                                  'Replace this message and all later messages?',
                                )
                              )
                                void send(text, undefined, m.id).catch(
                                  () => {},
                                );
                            }}
                          >
                            Edit & resend
                          </button>
                        )}
                        {m.role === 'user' &&
                          i === messages.length - 1 &&
                          !busy && (
                            <button
                              type="button"
                              onClick={() =>
                                void send(m.content, undefined, m.id).catch(
                                  () => {},
                                )
                              }
                            >
                              Retry
                            </button>
                          )}
                        {m.role === 'assistant' &&
                          i === messages.length - 1 &&
                          messages[i - 1]?.role === 'user' && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => {
                                const previous = messages[i - 1];
                                void send(
                                  previous.content,
                                  undefined,
                                  previous.id,
                                ).catch(() => {});
                              }}
                            >
                              Regenerate
                            </button>
                          )}
                        {m.role === 'assistant' &&
                          !busy &&
                          (['helpful', 'unhelpful'] as const).map((rating) => (
                            <button
                              key={rating}
                              type="button"
                              aria-pressed={m.rating === rating}
                              onClick={() => {
                                void api(
                                  `/conversations/${active}/messages/${m.id}/feedback`,
                                  {
                                    method: 'POST',
                                    headers: headers(session),
                                    body: JSON.stringify({ rating }),
                                  },
                                )
                                  .then(() =>
                                    setMessages((old) =>
                                      old.map((item) =>
                                        item.id === m.id
                                          ? { ...item, rating }
                                          : item,
                                      ),
                                    ),
                                  )
                                  .catch((e) => setError(e.message));
                              }}
                            >
                              {rating === 'helpful' ? 'Helpful' : 'Not helpful'}
                            </button>
                          ))}
                      </div>
                    )}
                  </article>
                ))}
                <div ref={tail} />
              </div>
            </div>
            {profile && (
              <div className="conversation-documents">
                <span>
                  Profile: {profile.name}
                  <button
                    type="button"
                    onClick={() => setProfile(null)}
                    aria-label="Remove profile context"
                  >
                    ×
                  </button>
                </span>
              </div>
            )}
            {documents.length > 0 && (
              <div className="conversation-documents">
                {documents.map((doc) => (
                  <span key={doc.id}>
                    {doc.name}
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`Remove ${doc.name}`}
                      onClick={() => {
                        void api(
                          `/conversations/${active}/documents/${doc.id}`,
                          { method: 'DELETE', headers: headers(session) },
                        )
                          .then(() =>
                            setDocuments((old) =>
                              old.filter((item) => item.id !== doc.id),
                            ),
                          )
                          .catch((e) => setError(e.message));
                      }}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            {error && (
              <div role="alert" className="conversation-error">
                {error}
              </div>
            )}
            {progress && (
              <div role="status" className="conversation-error">
                {progress}
              </div>
            )}
            <form className="conversation-composer" onSubmit={submit}>
              <label htmlFor="conversation-input" className="sr-only">
                Message
              </label>
              <textarea
                id="conversation-input"
                placeholder="Ask anything about your research…"
                value={input}
                maxLength={16000}
                disabled={!session || busy}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (input.trim() && !busy)
                      e.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="conversation-composer-bottom">
                <label className="conversation-research">
                  <input
                    type="checkbox"
                    checked={research}
                    disabled={busy}
                    onChange={(e) => setResearch(e.target.checked)}
                  />
                  <Search size={14} />
                  <span>Search research records for the next message</span>
                </label>
                {busy ? (
                  <button
                    className="conversation-send"
                    type="button"
                    onClick={() => stopGeneration.current?.()}
                  >
                    <Square size={14} fill="currentColor" /> Stop
                  </button>
                ) : (
                  <button
                    className="conversation-send"
                    type="submit"
                    disabled={!session || !input.trim()}
                  >
                    Send <ArrowUp size={17} />
                  </button>
                )}
              </div>
            </form>
            <p className="conversation-footnote">
              Enter to send <span>·</span> Shift + Enter for a new line{' '}
              <span>·</span> Verify important claims
            </p>
          </>
        )}
      </section>
    </main>
  );
}
