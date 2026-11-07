'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { Icon } from './Icon';
import type { Expert } from '../lib/types';

type GraphNode = {
  key: string;
  label: string;
  kind: 'match' | 'paper' | 'collaborator';
  x: number;
  y: number;
  personId?: number;
  paperId?: string;
  year?: number | null;
  source?: string;
};
type GraphEdge = { from: string; to: string };
type View = { zoom: number; angle: number; x: number; y: number };
type Drag = {
  pointerId: number;
  kind: 'node' | 'canvas';
  key?: string;
  startX: number;
  startY: number;
  x: number;
  y: number;
  moved: boolean;
};
const initialView: View = { zoom: 1, angle: 0, x: 0, y: 0 };
const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

// Edges are drawn only for authors named in the returned publication evidence.
function buildGraph(experts: Expert[]) {
  const matches = experts.slice(0, 5);
  const people = new Map<
    number,
    { name: string; kind: 'match' | 'collaborator' }
  >();
  const papers = new Map<
    string,
    { title: string; year: number | null; source: string; authors: Set<number> }
  >();
  for (const expert of matches)
    people.set(expert.person_id, { name: expert.name, kind: 'match' });
  for (const expert of matches)
    for (const record of expert.evidence.slice(0, 2)) {
      const paper = papers.get(record.paper_id) || {
        title: record.title,
        year: record.year,
        source: record.source,
        authors: new Set<number>(),
      };
      paper.authors.add(expert.person_id);
      for (const author of record.collaborators) {
        paper.authors.add(author.person_id);
        if (!people.has(author.person_id))
          people.set(author.person_id, {
            name: author.name,
            kind: 'collaborator',
          });
      }
      papers.set(record.paper_id, paper);
    }
  const nodes: GraphNode[] = [];
  for (const [id, person] of people)
    nodes.push({
      key: `author:${id}`,
      label: person.name,
      kind: person.kind,
      personId: id,
      x: 0,
      y: 0,
    });
  for (const [id, paper] of papers)
    nodes.push({
      key: `paper:${id}`,
      label: paper.title,
      kind: 'paper',
      paperId: id,
      year: paper.year,
      source: paper.source,
      x: 0,
      y: 0,
    });
  const edges: GraphEdge[] = [];
  for (const [id, paper] of papers)
    for (const author of paper.authors)
      if (people.has(author))
        edges.push({ from: `author:${author}`, to: `paper:${id}` });
  const count = nodes.length;
  nodes.forEach((node, i) => {
    const angle = i * 2.399963;
    const radius = 80 + 300 * Math.sqrt((i + 1) / Math.max(1, count));
    node.x = 600 + Math.cos(angle) * radius;
    node.y = 360 + Math.sin(angle) * radius * 0.8;
  });
  const lookup = new Map(nodes.map((node, index) => [node.key, index]));
  const stride = Math.max(1, Math.ceil(count / 250));
  for (let step = 0; step < 140; step++) {
    const dx = new Float64Array(count),
      dy = new Float64Array(count);
    for (let i = 0; i < count; i++)
      for (let j = i + 1; j < count; j += stride) {
        const x = nodes[i].x - nodes[j].x || 0.01,
          y = nodes[i].y - nodes[j].y || 0.01;
        const distance = Math.max(12, Math.hypot(x, y)),
          force = Math.min(8, 4000 / (distance * distance));
        dx[i] += (x / distance) * force;
        dy[i] += (y / distance) * force;
        dx[j] -= (x / distance) * force;
        dy[j] -= (y / distance) * force;
      }
    for (const edge of edges) {
      const a = lookup.get(edge.from)!,
        b = lookup.get(edge.to)!;
      const x = nodes[b].x - nodes[a].x,
        y = nodes[b].y - nodes[a].y,
        d = Math.max(1, Math.hypot(x, y));
      const force = (d - 130) * 0.01;
      dx[a] += (x / d) * force;
      dy[a] += (y / d) * force;
      dx[b] -= (x / d) * force;
      dy[b] -= (y / d) * force;
    }
    nodes.forEach((node, i) => {
      node.x = clamp(node.x + dx[i] + (600 - node.x) * 0.0015, 70, 1130);
      node.y = clamp(node.y + dy[i] + (360 - node.y) * 0.0015, 55, 665);
    });
  }
  return {
    nodes,
    edges,
    lookup,
    paperCount: papers.size,
    authorCount: people.size,
    matchCount: matches.length,
  };
}

export function EvidenceGraph({ experts }: { experts: Expert[] }) {
  const graph = useMemo(() => buildGraph(experts), [experts]);
  const [active, setActive] = useState<string | null>(null);
  const [view, setView] = useState<View>(initialView);
  const svg = useRef<SVGSVGElement>(null),
    scene = useRef<SVGGElement>(null),
    drag = useRef<Drag | null>(null),
    suppressClick = useRef(false);
  // New search results should not inherit dragged positions or focus from the last search.
  useEffect(() => {
    setActive(null);
    setView(initialView);
  }, [graph]);
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const matrix = element.getScreenCTM();
      const cursor = matrix
        ? new DOMPoint(event.clientX, event.clientY).matrixTransform(
            matrix.inverse(),
          )
        : { x: 600, y: 360 };
      setView((previous) => {
        const zoom = clamp(
            previous.zoom * Math.exp(-event.deltaY * 0.001),
            0.5,
            3,
          ),
          ratio = zoom / previous.zoom;
        return {
          ...previous,
          zoom,
          x: cursor.x - 600 - (cursor.x - 600 - previous.x) * ratio,
          y: cursor.y - 360 - (cursor.y - 360 - previous.y) * ratio,
        };
      });
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, [graph.paperCount]);
  const current = graph.nodes.find((node) => node.key === active) || null;
  const neighbors = useMemo(
    () =>
      new Set(
        graph.edges.flatMap((edge) =>
          edge.from === active
            ? [edge.to]
            : edge.to === active
              ? [edge.from]
              : [],
        ),
      ),
    [graph, active],
  );
  const point = (node: GraphNode) => node;
  function startDrag(
    event: ReactPointerEvent<SVGElement>,
    kind: 'node' | 'canvas',
    key?: string,
  ) {
    if (event.button !== 0) return;
    event.stopPropagation();
    suppressClick.current = false;
    drag.current = {
      pointerId: event.pointerId,
      kind,
      key,
      startX: event.clientX,
      startY: event.clientY,
      x: event.clientX,
      y: event.clientY,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    if (key) setActive(key);
  }
  function moveDrag(event: ReactPointerEvent<SVGElement>) {
    const state = drag.current;
    if (!state || state.pointerId !== event.pointerId) return;
    event.stopPropagation();
    if (
      Math.hypot(event.clientX - state.startX, event.clientY - state.startY) > 4
    )
      state.moved = true;
    const bounds = svg.current?.getBoundingClientRect();
    if (bounds?.width) {
      const turn = ((event.clientX - state.x) / bounds.width) * 240;
      setView((previous) => ({ ...previous, angle: previous.angle + turn }));
    }
    state.x = event.clientX;
    state.y = event.clientY;
  }
  function finishDrag(event: ReactPointerEvent<SVGElement>) {
    if (drag.current?.pointerId === event.pointerId) {
      suppressClick.current = drag.current.moved;
      drag.current = null;
    }
  }
  if (!experts.length || !graph.paperCount)
    return (
      <section className="graph-section" aria-label="Research graph">
        <div className="graph-empty">
          <span className="graph-icon">
            <Icon name="graph" size={22} />
          </span>
          <h3>Evidence graph appears with your results</h3>
          <p>
            Search for a topic to see researchers, papers and their connections
            come together.
          </p>
        </div>
      </section>
    );
  return (
    <section className="graph-section" aria-labelledby="graph-title">
      <div className="network-heading">
        <div>
          <span className="network-kicker">
            <span /> EXPLORE THE EVIDENCE
          </span>
          <h2 id="graph-title">
            Every connection
            <br />
            <em>has a story.</em>
          </h2>
          <p>
            Trace the people behind the research. Hover over a node to reveal
            its connections; open a researcher to explore their work.
          </p>
        </div>
        <div className="network-header-meta">
          <span>RESEARCH GRAPH</span>
          <strong>
            {String(graph.paperCount).padStart(2, '0')} <small>papers</small>
          </strong>
          <strong>
            {String(graph.authorCount).padStart(2, '0')} <small>people</small>
          </strong>
          <span>↗ SOURCED FROM DBLP</span>
        </div>
      </div>
      <div className="network-toolbar">
        <div className="network-key" aria-label="Graph legend">
          <span>
            <i className="key-match" />
            Researchers
          </span>
          <span>
            <i className="key-paper" />
            Publications
          </span>
          <span>
            <i className="key-collaborator" />
            Coauthors
          </span>
        </div>
      </div>
      <div
        className="network-stage"
        role="region"
        aria-label="Interactive publication and researcher network"
      >
        <svg
          ref={svg}
          className="network-graph"
          viewBox="0 0 1200 720"
          role="group"
          tabIndex={0}
          aria-label="Research evidence network. Drag to rotate, scroll to zoom; use left and right arrows to rotate and plus or minus to zoom."
          onKeyDown={(event) => {
            if (event.target !== event.currentTarget) return;
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
              event.preventDefault();
              setView((previous) => ({
                ...previous,
                angle: previous.angle + (event.key === 'ArrowRight' ? 15 : -15),
              }));
            } else if (
              event.key === '+' ||
              event.key === '=' ||
              event.key === '-'
            ) {
              event.preventDefault();
              setView((previous) => ({
                ...previous,
                zoom: clamp(
                  previous.zoom * (event.key === '-' ? 1 / 1.25 : 1.25),
                  0.5,
                  3,
                ),
              }));
            } else if (event.key === '0') {
              setView(initialView);
            }
          }}
          onPointerDown={(event) => startDrag(event, 'canvas')}
          onPointerMove={moveDrag}
          onPointerUp={finishDrag}
          onPointerCancel={finishDrag}
          onPointerLeave={() => {
            if (!drag.current) setActive(null);
          }}
        >
          <g
            ref={scene}
            transform={`translate(${600 + view.x} ${360 + view.y}) scale(${view.zoom}) rotate(${view.angle}) translate(-600 -360)`}
          >
            {graph.edges.map((edge) => {
              const a = point(graph.nodes[graph.lookup.get(edge.from)!]),
                b = point(graph.nodes[graph.lookup.get(edge.to)!]);
              const highlighted =
                !!current &&
                (edge.from === current.key || edge.to === current.key);
              return (
                <line
                  key={`${edge.from}-${edge.to}`}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  className={`network-edge ${current && !highlighted ? 'is-dimmed' : ''} ${highlighted ? 'is-highlighted' : ''}`}
                />
              );
            })}
            {graph.nodes.map((node) => {
              const location = point(node),
                highlighted = node.key === current?.key,
                dimmed = !!current && !highlighted && !neighbors.has(node.key);
              const kind =
                node.kind === 'paper'
                  ? 'Publication'
                  : node.kind === 'match'
                    ? 'Researcher'
                    : 'Coauthor';
              return (
                <g
                  key={node.key}
                  className={`network-node node-${node.kind} ${highlighted ? 'is-selected' : ''} ${neighbors.has(node.key) ? 'is-connected' : ''} ${dimmed ? 'is-dimmed' : ''}`}
                  transform={`translate(${location.x} ${location.y})`}
                  role={node.personId !== undefined ? 'link' : 'button'}
                  tabIndex={0}
                  aria-label={`${kind}: ${node.label}`}
                  onPointerEnter={() => setActive(node.key)}
                  onPointerLeave={() => {
                    if (!drag.current) setActive(null);
                  }}
                  onFocus={() => setActive(node.key)}
                  onBlur={() => setActive(null)}
                  onPointerDown={(event) => startDrag(event, 'node', node.key)}
                  onPointerMove={moveDrag}
                  onPointerUp={finishDrag}
                  onPointerCancel={finishDrag}
                  onClick={() => {
                    if (!suppressClick.current && node.personId !== undefined)
                      window.location.assign(`/experts/${node.personId}`);
                  }}
                  onKeyDown={(event) => {
                    if (
                      (event.key === 'Enter' || event.key === ' ') &&
                      node.personId !== undefined
                    ) {
                      event.preventDefault();
                      window.location.assign(`/experts/${node.personId}`);
                    } else if (event.key === 'Escape') setActive(null);
                  }}
                >
                  <circle className="node-hit-area" r="18" />
                  <circle
                    className="node-core"
                    r={
                      node.kind === 'paper' ? 8 : node.kind === 'match' ? 8 : 7
                    }
                  />
                  <text
                    y="25"
                    textAnchor="middle"
                    transform={`rotate(${-view.angle} 0 25)`}
                  >
                    {node.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
        <div className="network-hint">
          DRAG TO ROTATE · SCROLL TO ZOOM · HOVER TO EXPLORE
        </div>
      </div>
      <div className="network-detail" aria-live="polite">
        {current ? (
          <div>
            <span className="network-detail-label">
              {current.kind === 'paper'
                ? `THE PUBLICATION · ${current.year || 'YEAR UNKNOWN'} · ${(current.source || 'DBLP').toUpperCase()}`
                : current.kind === 'match'
                  ? 'THE RESEARCHER'
                  : 'THE COAUTHOR'}
            </span>
            <strong>{current.label}</strong>
            <p>
              {current.kind === 'paper'
                ? `This publication connects ${neighbors.size} ${neighbors.size === 1 ? 'researcher' : 'researchers'} in your results. Explore the lines to see who contributed to this work.`
                : `Their work connects to ${neighbors.size} ${neighbors.size === 1 ? 'publication' : 'publications'} in this view. Follow a line to discover the research behind the connection.`}
            </p>
            <span className="network-detail-source">
              {current.kind === 'paper'
                ? `DBLP RECORD · ${current.paperId}`
                : 'SELECT THE NODE TO OPEN THEIR PROFILE ↗'}
            </span>
          </div>
        ) : (
          <div>
            <span className="network-detail-label">A CLOSER LOOK</span>
            <strong>Follow the work. Find the people.</strong>
            <p>
              Hover over any point to bring its connections into focus and
              discover the evidence behind them.
            </p>
            <span className="network-detail-source">
              RESEARCHERS · PUBLICATIONS · COAUTHORS
            </span>
          </div>
        )}
      </div>
      <p className="network-footnote">
        Showing up to {graph.matchCount} search matches and two returned papers
        per researcher, with their listed coauthors. This is a view of returned
        evidence, not the complete research network. Positions are illustrative.
      </p>
    </section>
  );
}
