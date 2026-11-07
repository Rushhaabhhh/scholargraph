'use client';
import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';

const builders = [
  { name: 'layout', color: '#b8d6a4' },
  { name: 'type', color: '#dbcbaa' },
  { name: 'graph', color: '#9dc9bd' },
  { name: 'detail', color: '#d2baa7' },
  { name: 'signal', color: '#b7bddf' },
  { name: 'structure', color: '#c8d7b3' },
  { name: 'data', color: '#a4c9c4' },
  { name: 'search', color: '#d9c9a2' },
];
type Task = { selector: string; mode: 'text' | 'box' };
const waves: { scrollTo: string; tasks: Task[] }[] = [
  {
    scrollTo: '.hero-title-wrap',
    tasks: [{ selector: '.hero-brand', mode: 'box' }],
  },
  {
    scrollTo: '.hero-title-wrap',
    tasks: [
      { selector: '.hero-title-wrap h1', mode: 'text' },
      { selector: '.hero-title-meta', mode: 'text' },
    ],
  },
  {
    scrollTo: '.hero-visual',
    tasks: [
      { selector: '.hero-visual', mode: 'box' },
      { selector: '.hero-visual-inner', mode: 'box' },
      { selector: '.visual-label', mode: 'text' },
      { selector: '.visual-card', mode: 'box' },
      { selector: '.visual-notation', mode: 'text' },
    ],
  },
  {
    scrollTo: '.hero-intro',
    tasks: [
      { selector: '.hero-intro > div:first-child', mode: 'text' },
      { selector: '.hero-numbers', mode: 'text' },
    ],
  },
  {
    scrollTo: '.method-header',
    tasks: [
      { selector: '.method-header', mode: 'text' },
      { selector: '.method-title', mode: 'text' },
    ],
  },
  {
    scrollTo: '.method-grid',
    tasks: [
      { selector: '.method-list', mode: 'box' },
      { selector: '.method-detail', mode: 'box' },
    ],
  },
  {
    scrollTo: '.search-heading',
    tasks: [
      { selector: '.search-heading .section-kicker', mode: 'text' },
      { selector: '.search-heading h2', mode: 'text' },
      { selector: '.search-heading p', mode: 'text' },
      { selector: '.backend-pill', mode: 'box' },
      { selector: '.search-composer', mode: 'box' },
      { selector: '.discovery-form-heading', mode: 'text' },
      { selector: '.search-input-row', mode: 'box' },
      { selector: '.filter-row', mode: 'box' },
    ],
  },
];

/** Independent cursor choreography over the actual page, with no cloned controls. */
export function CursorSwarm() {
  const layer = useRef<HTMLDivElement>(null),
    finishRef = useRef<() => void>(() => {});
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (
      (typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
      window.location.hash ||
      window.location.search ||
      window.scrollY > 40
    )
      return;
    try {
      if (
        sessionStorage.getItem('scholargraph-results') ||
        sessionStorage.getItem('hiresense-results')
      )
        return;
    } catch {
      /* Storage can be unavailable. */
    }
    const overlay = layer.current;
    if (!overlay) return;
    const cursors = Array.from(
      overlay.querySelectorAll<HTMLElement>('.swarm-cursor'),
    );
    const outlines = Array.from(
      overlay.querySelectorAll<HTMLElement>('.swarm-outline'),
    );
    if (!cursors.length || cursors.length !== outlines.length) return;
    // The small-screen sidebar is not rendered; never schedule invisible targets.
    const tasks = waves
      .map((wave) => ({
        target: document.querySelector<HTMLElement>(wave.scrollTo),
        items: wave.tasks.flatMap((task) =>
          Array.from(document.querySelectorAll<HTMLElement>(task.selector))
            .filter((element) => {
              const rect = element.getBoundingClientRect();
              return rect.width > 0 && rect.height > 0;
            })
            .map((element) => ({ element, mode: task.mode })),
        ),
      }))
      .filter((wave) => wave.items.length > 0);
    const elements = Array.from(
      new Set(tasks.flatMap((wave) => wave.items.map((item) => item.element))),
    );
    if (!elements.length) return;
    const originalClips = new Map(
      elements.map((element) => [element, element.style.clipPath]),
    );
    let done = false;
    const previousScrollBehavior =
      document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = 'auto';
    gsap.set(elements, { clipPath: 'inset(0 100% 100% 0)' });
    gsap.set(cursors, {
      x: window.innerWidth * 0.5,
      y: window.innerHeight * 0.43,
      opacity: 0,
      scale: 0.9,
    });
    gsap.set(outlines, { opacity: 0 });
    setRunning(true);
    const scroll = { y: window.scrollY };
    const tl = gsap.timeline({ paused: true });
    function finish() {
      if (done) return;
      done = true;
      tl.kill();
      gsap.killTweensOf(cursors);
      gsap.killTweensOf(outlines);
      for (const [element, clip] of originalClips)
        element.style.clipPath = clip;
      document.documentElement.style.scrollBehavior = previousScrollBehavior;
      window.removeEventListener('wheel', interrupt, true);
      window.removeEventListener('touchstart', interrupt, true);
      window.removeEventListener('pointerdown', interrupt, true);
      window.removeEventListener('keydown', interrupt, true);
      setRunning(false);
    }
    finishRef.current = finish;
    function interrupt(event: Event) {
      if (event.isTrusted) finish();
    }
    window.addEventListener('wheel', interrupt, {
      capture: true,
      passive: true,
    });
    window.addEventListener('touchstart', interrupt, {
      capture: true,
      passive: true,
    });
    window.addEventListener('pointerdown', interrupt, true);
    window.addEventListener('keydown', interrupt, true);
    tasks.forEach((wave, index) => {
      const start = 0.2 + index * 1.95;
      if (wave.target && index > 0) {
        const target = wave.target;
        tl.to(
          scroll,
          {
            y: () =>
              Math.max(
                0,
                Math.min(
                  document.documentElement.scrollHeight - window.innerHeight,
                  window.scrollY +
                    target.getBoundingClientRect().top -
                    window.innerHeight * 0.12,
                ),
              ),
            duration: 0.58,
            ease: 'power2.inOut',
            onUpdate: () => window.scrollTo(0, scroll.y),
          },
          start,
        );
      }
      wave.items
        .slice(0, cursors.length)
        .forEach(({ element, mode }, agent) => {
          const cursor = cursors[agent],
            outline = outlines[agent];
          const offset = agent * 0.045,
            arrival = start + 0.65 + offset,
            draw = arrival + 0.36;
          const position = () => {
            const rect = element.getBoundingClientRect();
            return {
              x: Math.max(2, Math.min(window.innerWidth - 12, rect.left)),
              y: Math.max(
                2,
                Math.min(
                  window.innerHeight - 12,
                  mode === 'text'
                    ? rect.top +
                        Math.min(rect.height, window.innerHeight) * 0.65
                    : rect.top,
                ),
              ),
            };
          };
          tl.to(
            cursor,
            {
              opacity: 1,
              scale: 1,
              x: () => position().x - 2,
              y: () => position().y - 2,
              duration: 0.34,
              ease: 'power2.inOut',
            },
            arrival,
          );
          const progress = { value: 0 };
          tl.to(
            progress,
            {
              value: 1,
              duration: 0.68,
              ease: 'power1.inOut',
              onStart: () => {
                const r = element.getBoundingClientRect(),
                  label = outline.querySelector('span');
                if (label)
                  label.textContent = `${Math.round(r.width)} × ${Math.round(r.height)}`;
                gsap.set(outline, { opacity: 1 });
              },
              onUpdate: () => {
                const r = element.getBoundingClientRect(),
                  v = progress.value;
                // The cursor tip remains attached to the growing right edge / bottom corner.
                const right = r.left + r.width * v,
                  bottom =
                    mode === 'text'
                      ? r.top + r.height * 0.65
                      : r.top + r.height * v;
                element.style.clipPath =
                  mode === 'text'
                    ? `inset(0 ${(1 - v) * 100}% 0 0)`
                    : `inset(0 ${(1 - v) * 100}% ${(1 - v) * 100}% 0)`;
                gsap.set(outline, {
                  left: r.left,
                  top: r.top,
                  width: r.width * v,
                  height: mode === 'text' ? r.height : r.height * v,
                });
                gsap.set(cursor, { x: right - 2, y: bottom - 2 });
              },
              onComplete: () => {
                element.style.clipPath = 'inset(0 0 0 0)';
              },
            },
            draw,
          );
          tl.to(outline, { opacity: 0, duration: 0.18 }, draw + 0.7);
        });
      for (let agent = wave.items.length; agent < cursors.length; agent++)
        tl.to(cursors[agent], { opacity: 0, duration: 0.25 }, start + 0.55);
    });
    tl.to(
      cursors,
      { opacity: 0, scale: 0.85, duration: 0.32, stagger: 0.02 },
      0.2 + tasks.length * 1.95,
    ).add(finish);
    const start = window.setTimeout(() => {
      if (!done) tl.play();
    }, 100);
    return () => {
      window.clearTimeout(start);
      finish();
    };
  }, []);
  return (
    <div
      ref={layer}
      className={`swarm-layer ${running ? 'is-running' : ''}`}
      aria-hidden={!running}
    >
      {builders.map((builder) => (
        <div
          key={`outline-${builder.name}`}
          className="swarm-outline"
          aria-hidden="true"
          style={{ '--cursor-color': builder.color } as React.CSSProperties}
        >
          <span />
        </div>
      ))}
      {builders.map((builder) => (
        <div
          key={builder.name}
          className="swarm-cursor"
          aria-hidden="true"
          style={{ '--cursor-color': builder.color } as React.CSSProperties}
        >
          <svg viewBox="0 0 24 28" width="19" height="22" aria-hidden="true">
            <path
              d="M3 2v19l5.2-4 3.5 7 3-1.5-3.4-6.7 6.8-.5z"
              fill="currentColor"
              stroke="#111510"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
          <span>{builder.name}</span>
        </div>
      ))}
      {running && (
        <button
          type="button"
          className="swarm-skip"
          onClick={() => finishRef.current()}
        >
          Skip intro <span>ESC</span>
        </button>
      )}
    </div>
  );
}
