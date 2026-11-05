'use client';
import {useMemo,useState} from 'react';
import Link from 'next/link';
import type {Expert} from '../lib/types';
import {Icon} from './Icon';

type GraphAuthor={id:number;name:string;kind:'match'|'collaborator';x:number;y:number};
type GraphPaper={id:string;title:string;year:number|null;source:string;authors:number[];x:number;y:number};
export function EvidenceGraph({experts}:{experts:Expert[]}){
 const graph=useMemo(()=>{
  const matches=experts.slice(0,5);const main:GraphAuthor[]=matches.map((e,i)=>({id:e.person_id,name:e.name,kind:'match',x:128,y:0}));
  const paperMap=new Map<string,{title:string;year:number|null;source:string;authors:Set<number>}>();
  for(const expert of matches)for(const evidence of expert.evidence.slice(0,2)){const item=paperMap.get(evidence.paper_id)||{title:evidence.title,year:evidence.year,source:evidence.source,authors:new Set<number>()};item.authors.add(expert.person_id);evidence.collaborators.forEach(c=>item.authors.add(c.person_id));paperMap.set(evidence.paper_id,item)}
  const people=new Map<number,string>();for(const e of matches)people.set(e.person_id,e.name);
  for(const expert of matches)for(const evidence of expert.evidence.slice(0,2))for(const p of evidence.collaborators)people.set(p.person_id,p.name);
  const paperEntries=[...paperMap.entries()].slice(0,10);const height=Math.max(390,paperEntries.length*82+70);
  const yAt=(i:number,count:number)=>Math.round(55+(i+1)*(height-100)/(count+1));
  const papers:GraphPaper[]=paperEntries.map(([id,p],i)=>({id,title:p.title,year:p.year,source:p.source,authors:[...p.authors],x:500,y:yAt(i,paperEntries.length)}));
  const matchPositions=new Map(main.map((m,i)=>[m.id,yAt(i,main.length)]));main.forEach(m=>m.y=matchPositions.get(m.id)||60);
  const matchIds=new Set(main.map(a=>a.id));const adjacent=[...new Set(papers.flatMap(p=>p.authors).filter(id=>!matchIds.has(id)))].slice(0,16);
  const others:GraphAuthor[]=adjacent.map((id,i)=>({id,name:people.get(id)||`Author ${id}`,kind:'collaborator',x:872,y:yAt(i,adjacent.length)}));
  const authors=[...main,...others];const paperIds=new Set(papers.map(p=>p.id));
  const edges=papers.flatMap(p=>p.authors.filter(id=>authors.some(a=>a.id===id)).map(id=>({from:authors.find(a=>a.id===id)!,to:p,paper:p.id})));
  return {authors,papers,edges,height,paperIds};
 },[experts]);
 const [selected,setSelected]=useState<string|null>(null);const current=graph.papers.find(p=>p.id===selected)||null;
 if(!experts.length||!graph.papers.length)return <section className="graph-section" aria-label="Research graph"><div className="graph-empty"><span className="graph-icon"><Icon name="graph" size={22}/></span><h3>Evidence graph appears with your results</h3><p>Run a search to map returned researchers, their supporting papers, and the collaborators listed in those papers.</p></div></section>;
 return <section className="graph-section" aria-labelledby="graph-title">
  <div className="graph-heading"><div><span className="eyebrow">EVIDENCE, CONNECTED</span><h2 id="graph-title">Research graph</h2><p>Explore the relationships behind this search. Each link comes from a returned publication record.</p></div><span className="graph-source"><i/> DBLP-SOURCED LINKS</span></div>
  <div className="graph-legend"><span><i className="legend-author"/>Matched researchers</span><span><i className="legend-paper"/>Returned papers</span><span><i className="legend-collab"/>Listed coauthors</span><span className="graph-count">{graph.papers.length} papers · {graph.authors.length} people shown</span></div>
  <div className="graph-scroll" role="region" aria-label="Interactive publication and author graph" tabIndex={0}><div className="graph-canvas" style={{height:graph.height}}><svg className="graph-edges" viewBox={`0 0 1000 ${graph.height}`} preserveAspectRatio="none" aria-hidden="true">{graph.edges.map((edge,index)=>{const sourceX=edge.from.kind==='match'?210:790;const targetX=edge.to.x===500?500:500;const isSelected=selected===edge.paper||selected===null;return <path key={`${edge.from.id}-${edge.paper}-${index}`} d={`M ${sourceX} ${edge.from.y} C ${(sourceX+targetX)/2} ${edge.from.y}, ${(sourceX+targetX)/2} ${edge.to.y}, ${targetX} ${edge.to.y}`} className={`graph-edge ${edge.from.kind==='match'?'match-edge':'collab-edge'} ${isSelected?'':'dimmed'}`} onMouseEnter={()=>setSelected(edge.paper)}/>})}</svg>
   <div className="graph-column-label match-label">SEARCH MATCHES</div><div className="graph-column-label paper-label">EVIDENCE PAPERS</div><div className="graph-column-label collab-label">COAUTHORS ON PAPER</div>
   {graph.authors.map(author=><Link key={`${author.kind}-${author.id}`} href={`/experts/${author.id}`} className={`graph-person graph-${author.kind} ${current&&graph.edges.some(e=>e.paper===current.id&&e.from.id===author.id)?'connected':''}`} style={{left:`${author.x/10}%`,top:author.y}} title={`Open ${author.name}'s sourced profile`}><span className="graph-person-dot">{author.kind==='match'?'R':'↗'}</span><span className="graph-person-copy"><b>{author.name}</b><small>{author.kind==='match'?'Search result':'Author on cited paper'}</small></span><Icon name="arrow" size={14}/></Link>)}
   {graph.papers.map(paper=><button type="button" key={paper.id} onFocus={()=>setSelected(paper.id)} onMouseEnter={()=>setSelected(paper.id)} onClick={()=>setSelected(paper.id)} className={`graph-paper ${selected===paper.id?'selected':''}`} style={{left:'50%',top:paper.y}} aria-pressed={selected===paper.id} title={`Show source details for ${paper.title}`}><span className="paper-dot"><Icon name="bookmark" size={14}/></span><span><b>{paper.title}</b><small>{paper.year||'Year unavailable'} · {paper.source.toUpperCase()} · {paper.id}</small></span></button>)}
  </div></div>
  <div className="graph-detail" aria-live="polite"><div className="graph-detail-icon"><Icon name="bookmark" size={17}/></div>{current?<><div><span className="eyebrow">SELECTED PUBLICATION · {current.year||'YEAR UNKNOWN'} · {current.source.toUpperCase()}</span><strong>{current.title}</strong><small>Source record {current.id}. Connected people shown here are returned author records for this publication.</small></div><button type="button" className="detail-clear" onClick={()=>setSelected(null)}>Clear focus</button></>:<div><span className="eyebrow">HOW TO READ THIS</span><strong>Follow a line from a researcher to a paper.</strong><small>Focus a paper to highlight the returned search match and coauthors tied to that evidence.</small></div>}</div>
  <p className="graph-footnote">This view uses up to five search matches, two returned papers per match, and listed collaborators. It is a slice of search evidence, not a complete collaboration network. Select any person to open their DBLP-backed profile.</p>
 </section>
}
