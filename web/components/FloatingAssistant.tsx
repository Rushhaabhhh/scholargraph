'use client';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent,
} from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { gsap } from 'gsap';
import { Bookmark, MoveDiagonal2, Sparkles } from 'lucide-react';
import { OPEN_ASSISTANT_EVENT, type AssistantProfile } from '../lib/assistant';
const ConversationContent = dynamic(
  () =>
    import('./ConversationWorkspace').then(
      (module) => module.ConversationContent,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="assistant-panel-loading">Preparing your assistant…</div>
    ),
  },
);
export function FloatingAssistant() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false),
    [visited, setVisited] = useState(false),
    [state, setState] = useState('idle');
  const [profileTarget, setProfileTarget] = useState<AssistantProfile | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const resize = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const [panelSize, setPanelSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const reduced = useReducedMotion();
  const report = useCallback((value: string) => setState(value), []);
  const resizePanel = (width: number, height: number) => {
    const mobile = window.innerWidth <= 600;
    const maxWidth = Math.max(1, window.innerWidth - (mobile ? 16 : 32));
    const maxHeight = Math.max(1, window.innerHeight - (mobile ? 110 : 140));
    setPanelSize({
      width: Math.min(maxWidth, Math.max(Math.min(320, maxWidth), width)),
      height: Math.min(maxHeight, Math.max(Math.min(350, maxHeight), height)),
    });
  };
  const startResize = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !panel.current) return;
    const rect = panel.current.getBoundingClientRect();
    resize.current = {
      x: event.clientX,
      y: event.clientY,
      width: rect.width,
      height: rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };
  const moveResize = (event: PointerEvent<HTMLButtonElement>) => {
    const start = resize.current;
    if (start)
      resizePanel(
        start.width + start.x - event.clientX,
        start.height + start.y - event.clientY,
      );
  };
  const resizeWithKeyboard = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (
      !panel.current ||
      !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
    )
      return;
    event.preventDefault();
    const rect = panel.current.getBoundingClientRect();
    const step = event.shiftKey ? 48 : 16;
    resizePanel(
      rect.width +
        (event.key === 'ArrowLeft'
          ? step
          : event.key === 'ArrowRight'
            ? -step
            : 0),
      rect.height +
        (event.key === 'ArrowUp'
          ? step
          : event.key === 'ArrowDown'
            ? -step
            : 0),
    );
  };
  useEffect(() => {
    const openProfile = (event: Event) => {
      const profile = (event as CustomEvent<AssistantProfile>).detail;
      if (!profile || !Number.isSafeInteger(profile.id) || profile.id <= 0 || !profile.name) return;
      setProfileTarget({ id: profile.id, name: profile.name });
      setVisited(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_ASSISTANT_EVENT, openProfile);
    return () => window.removeEventListener(OPEN_ASSISTANT_EVENT, openProfile);
  }, []);
  useEffect(() => {
    if (!button.current || reduced) return;
    const animation = gsap.fromTo(
      button.current,
      { opacity: 0, scale: 0.75 },
      { opacity: 1, scale: 1, duration: 0.7, ease: 'back.out(1.5)' },
    );
    return () => {
      animation.kill();
    };
  }, [pathname, reduced]);
  useEffect(() => {
    if (!open) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [open]);
  useEffect(() => {
    if (pathname === '/chat') setOpen(false);
  }, [pathname]);
  return (
    <div className="floating-assistant-root">
      <Link
        className={`floating-saved ${pathname === '/shortlist' ? 'is-active' : ''}`}
        href="/shortlist"
        aria-label="Open saved workspace"
        title="Saved workspace"
      >
        <Bookmark size={18} />
        <span>Saved workspace</span>
      </Link>
      {pathname !== '/chat' && (
        <>
          {visited && (
            <motion.div
              ref={panel}
              className="assistant-float-panel"
              role="dialog"
              aria-label="AI Assistant"
              aria-hidden={!open}
              style={
                panelSize
                  ? { width: panelSize.width, height: panelSize.height }
                  : undefined
              }
              initial={reduced ? false : { opacity: 0, y: 18, scale: 0.97 }}
              animate={
                open
                  ? { opacity: 1, y: 0, scale: 1, visibility: 'visible' }
                  : {
                      opacity: 0,
                      y: 12,
                      scale: 0.98,
                      transitionEnd: { visibility: 'hidden' },
                    }
              }
              transition={{
                duration: reduced ? 0 : 0.24,
                ease: [0.22, 1, 0.36, 1],
              }}
            >
              <button
                type="button"
                className="assistant-resize-handle"
                aria-label="Resize assistant panel"
                title="Drag to resize, or use arrow keys"
                onPointerDown={startResize}
                onPointerMove={moveResize}
                onPointerUp={() => {
                  resize.current = null;
                }}
                onPointerCancel={() => {
                  resize.current = null;
                }}
                onKeyDown={resizeWithKeyboard}
              >
                <MoveDiagonal2 size={13} strokeWidth={1.8} aria-hidden="true" />
              </button>
              <ConversationContent
                floating
                visible={open}
                onState={report}
                profileTarget={profileTarget}
                onClose={() => {
                  setOpen(false);
                  button.current?.focus();
                }}
              />
            </motion.div>
          )}
          <button
            ref={button}
            type="button"
            className={`intelligence-orb orb-${state} ${open ? 'is-open' : ''}`}
            aria-label={open ? 'Collapse AI assistant' : 'Open AI assistant'}
            aria-expanded={open}
            onClick={() => {
              setVisited(true);
              setOpen((v) => !v);
            }}
          >
            <span className="orb-ring orb-ring-one" />
            <span className="orb-ring orb-ring-two" />
            <span className="orb-particle p-one" />
            <span className="orb-particle p-two" />
            <span className="orb-particle p-three" />
            <span className="orb-core">
              <Sparkles size={22} />
            </span>
            <span className="orb-label">
              {state === 'listening'
                ? 'Listening'
                : state === 'processing'
                  ? 'Thinking'
                  : state === 'responding'
                    ? 'Responding'
                    : 'Ask Scholar'}
            </span>
          </button>
        </>
      )}
    </div>
  );
}
