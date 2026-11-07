'use client';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useReducedMotion } from 'motion/react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  ArrowRight,
  BookOpenCheck,
  Database,
  FileText,
  GitFork,
  ListOrdered,
  Network,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';

type Stage = {
  label: string;
  title: string;
  body: string;
  notes: [string, string];
  diagram: { icon: LucideIcon; label: string }[];
};
const stages: Stage[] = [
  {
    label: 'SOURCE',
    title: 'Start with the work.',
    body: 'Every discovery starts with public DBLP records: papers, researchers, venues and publication dates.',
    notes: ['Public research records', 'Source and date retained'],
    diagram: [
      { icon: Database, label: 'DBLP' },
      { icon: FileText, label: 'PAPERS' },
      { icon: UsersRound, label: 'AUTHORS' },
    ],
  },
  {
    label: 'CONNECT',
    title: 'See the connections.',
    body: 'Authorship, venues and collaborations link people to the work behind their expertise in a sourced research graph.',
    notes: ['Dated graph relationships', 'Evidence linked to its source'],
    diagram: [
      { icon: UserRound, label: 'PERSON' },
      { icon: Network, label: 'GRAPH' },
      { icon: GitFork, label: 'COLLABORATION' },
    ],
  },
  {
    label: 'RETRIEVE',
    title: 'Find the signal.',
    body: 'Lexical and semantic search work together to surface relevant publications and the researchers connected to them.',
    notes: ['Keyword and vector search', 'Publication evidence collected'],
    diagram: [
      { icon: Search, label: 'QUERY' },
      { icon: Sparkles, label: 'HYBRID SEARCH' },
      { icon: FileText, label: 'MATCHES' },
    ],
  },
  {
    label: 'RANK',
    title: 'Put relevance first.',
    body: 'A trained ranking model orders candidates using topical evidence, publication history and graph features.',
    notes: ['Learned ranking model', 'Scores are ordering signals'],
    diagram: [
      { icon: SlidersHorizontal, label: 'FEATURES' },
      { icon: Sparkles, label: 'MODEL' },
      { icon: ListOrdered, label: 'RANKING' },
    ],
  },
  {
    label: 'EXPLORE',
    title: 'Follow the evidence.',
    body: 'Review supporting papers, inspect researcher profiles and keep a shortlist for your next decision.',
    notes: ['Trace claims to publications', 'Save and compare researchers'],
    diagram: [
      { icon: BookOpenCheck, label: 'EVIDENCE' },
      { icon: UserRound, label: 'PROFILE' },
      { icon: UsersRound, label: 'SHORTLIST' },
    ],
  },
];

export function PipelineStory() {
  const [active, setActive] = useState(0);
  const root = useRef<HTMLElement>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced || !root.current) return;
    gsap.registerPlugin(ScrollTrigger);
    const ctx = gsap.context(() => {
      gsap.fromTo(
        '.method-reveal',
        { y: 45, opacity: 0 },
        {
          y: 0,
          opacity: 1,
          duration: 0.8,
          stagger: 0.14,
          scrollTrigger: {
            trigger: root.current,
            start: 'top 80%',
            once: true,
          },
        },
      );
    }, root);
    return () => ctx.revert();
  }, [reduced]);
  function moveTab(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight')
      next = (index + 1) % stages.length;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft')
      next = (index + stages.length - 1) % stages.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = stages.length - 1;
    else return;
    event.preventDefault();
    setActive(next);
    tabs.current[next]?.focus();
  }
  const stage = stages[active];
  return (
    <section
      ref={root}
      className="method-section"
      id="how-it-works"
      aria-labelledby="pipeline-title"
    >
      <div className="method-header method-reveal">
        <span>02 / THE METHOD</span>
        <span>FROM INFORMATION TO INSIGHT</span>
      </div>
      <h2 id="pipeline-title" className="method-title method-reveal">
        CONNECTIONS
        <br />
        <span>WITH CONTEXT.</span>
      </h2>
      <div className="method-grid method-reveal">
        <div
          className="method-list"
          role="tablist"
          aria-label="Pipeline steps"
          aria-orientation="vertical"
        >
          {stages.map((item, index) => (
            <button
              key={item.label}
              ref={(element) => {
                tabs.current[index] = element;
              }}
              id={`method-tab-${index}`}
              type="button"
              role="tab"
              aria-selected={active === index}
              aria-controls="method-panel"
              tabIndex={active === index ? 0 : -1}
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
              onClick={() => setActive(index)}
              onKeyDown={(event) => moveTab(event, index)}
            >
              <span className="method-number">
                {String(index + 1).padStart(2, '0')}
              </span>
              <b>{item.label}</b>
              <Plus
                className="method-plus"
                size={24}
                strokeWidth={1.5}
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
        <div
          className="method-detail"
          id="method-panel"
          role="tabpanel"
          aria-labelledby={`method-tab-${active}`}
        >
          <div className="method-stage-content" key={stage.label}>
            <div className="method-stage-kicker">
              <span>
                0{active + 1} / {stage.label}
              </span>
              <span>THE PROCESS</span>
            </div>
            <h3>{stage.title}</h3>
            <p>{stage.body}</p>
            <div
              className="method-diagram"
              aria-label={`${stage.label.toLowerCase()} process diagram`}
            >
              {stage.diagram.map(({ icon: DiagramIcon, label }, index) => (
                <div className="method-diagram-step" key={label}>
                  <div className="method-diagram-node">
                    <DiagramIcon
                      size={25}
                      strokeWidth={1.4}
                      aria-hidden="true"
                    />
                  </div>
                  <span>{label}</span>
                  {index < stage.diagram.length - 1 && (
                    <ArrowRight
                      className="method-diagram-arrow"
                      size={16}
                      aria-hidden="true"
                    />
                  )}
                </div>
              ))}
            </div>
            <div className="method-notes">
              {stage.notes.map((note) => (
                <span key={note}>{note}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
