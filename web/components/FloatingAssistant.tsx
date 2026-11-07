'use client';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { gsap } from 'gsap';
import { Bookmark, Sparkles } from 'lucide-react';
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
  const button = useRef<HTMLButtonElement>(null);
  const reduced = useReducedMotion();
  const report = useCallback((value: string) => setState(value), []);
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
              className="assistant-float-panel"
              role="dialog"
              aria-label="AI Assistant"
              aria-hidden={!open}
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
              <ConversationContent
                floating
                visible={open}
                onState={report}
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
