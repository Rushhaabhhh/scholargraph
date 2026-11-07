'use client';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { Brand } from './Brand';
import { ArrowDown, ArrowUpRight } from 'lucide-react';
const ResearchField = dynamic(
  () => import('./ResearchField').then((m) => m.ResearchField),
  { ssr: false },
);

export function ResearchHero({
  health,
}: {
  health: {
    status: string;
    papers: number;
    authors: number;
    model_version: string;
  } | null;
}) {
  const root = useRef<HTMLElement>(null);
  const prefersReduced = useReducedMotion();
  const [hasMounted, setHasMounted] = useState(false);
  const reduced = hasMounted && prefersReduced;
  const [webgl, setWebgl] = useState(false);
  useEffect(() => setHasMounted(true), []);
  useEffect(() => {
    try {
      const canvas = document.createElement('canvas');
      setWebgl(
        Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl')),
      );
    } catch {
      setWebgl(false);
    }
  }, []);
  useEffect(() => {
    if (reduced || !root.current) return;
    gsap.registerPlugin(ScrollTrigger);
    const ctx = gsap.context(() => {
      gsap.to('.hero-visual-inner', {
        yPercent: 14,
        ease: 'none',
        scrollTrigger: {
          trigger: '.hero-visual',
          start: 'top bottom',
          end: 'bottom top',
          scrub: true,
        },
      });
    }, root);
    return () => ctx.revert();
  }, [reduced]);
  return (
    <section ref={root} className="editorial-hero" aria-labelledby="hero-title">
      <div className="hero-brand">
        <Brand />
      </div>
      <motion.div
        className="hero-title-wrap"
        initial={reduced ? false : { opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
      >
        <h1 id="hero-title">
          THE RIGHT
          <br />
          <span>MINDS.</span>
        </h1>
        <div className="hero-title-meta">
          <span>
            RESEARCH
            <br />
            WITHOUT GUESSWORK.
          </span>
        </div>
      </motion.div>
      <div className="hero-visual">
        <div className="hero-visual-inner">
          <svg
            className="field-fallback"
            style={{ display: webgl && !reduced ? 'none' : undefined }}
            viewBox="0 0 600 500"
            aria-hidden="true"
          >
            <g fill="none" stroke="currentColor">
              <ellipse
                cx="300"
                cy="250"
                rx="210"
                ry="95"
                transform="rotate(-27 300 250)"
              />
              <ellipse
                cx="300"
                cy="250"
                rx="145"
                ry="205"
                transform="rotate(-27 300 250)"
              />
              <ellipse
                cx="300"
                cy="250"
                rx="200"
                ry="120"
                transform="rotate(28 300 250)"
              />
            </g>
            <g fill="currentColor">
              <circle cx="120" cy="280" r="3" />
              <circle cx="226" cy="98" r="3" />
              <circle cx="415" cy="164" r="4" />
              <circle cx="465" cy="305" r="3" />
              <circle cx="281" cy="397" r="3" />
              <circle cx="325" cy="251" r="5" />
            </g>
          </svg>
          {webgl && !reduced && <ResearchField />}
        </div>
        <div className="visual-label">
          <span>01 / THE RESEARCH FIELD</span>
          <span>PEOPLE · PAPERS · IDEAS</span>
        </div>
        <div className="visual-card">
          <span>
            FROM
            <br />
            QUESTION
            <br />
            TO CONNECTION<span className="card-arrow">↗</span>
          </span>
          <small>BUILT ON PUBLISHED WORK</small>
        </div>
        <div className="visual-notation">
          A WORLD OF IDEAS.
          <br />A PATH TO THE PEOPLE BEHIND THEM.
        </div>
      </div>
      <div className="hero-intro">
        <div>
          <p>Great research starts with the right people.</p>
          <p className="intro-secondary">
            Discover the experts behind the work, follow the evidence, and make
            your next connection with confidence.
          </p>
          <div className="editorial-actions">
            <a className="editorial-button" href="#search">
              Explore researchers <ArrowUpRight size={20} />
            </a>
            <a className="editorial-link" href="#how-it-works">
              How it works <ArrowDown size={19} />
            </a>
          </div>
        </div>
        <div className="hero-numbers">
          <div>
            <strong>{health ? health.papers.toLocaleString() : '—'}</strong>
            <span>PUBLICATION RECORDS</span>
          </div>
          <div>
            <strong>{health ? health.authors.toLocaleString() : '—'}</strong>
            <span>RESEARCHER RECORDS</span>
          </div>
          <small>{health ? 'CURRENT INDEX' : 'CONNECTING TO INDEX'}</small>
        </div>
      </div>
    </section>
  );
}
