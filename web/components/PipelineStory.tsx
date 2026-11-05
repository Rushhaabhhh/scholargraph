'use client';
import {useState} from 'react';
import {Icon} from './Icon';

const stages=[
 {number:'01',label:'Source',title:'Start with a research record',body:'The prepared DBLP corpus supplies publication titles, dates, author records, and source identifiers. This is the evidence base, not generated profiles.',tag:'DBLP · versioned artifacts'},
 {number:'02',label:'Connect',title:'Resolve people and relationships',body:'Author identities and coauthorship links are assembled from records. Graph edges stay tied to their supporting papers and years.',tag:'Identity · sourced edges'},
 {number:'03',label:'Retrieve',title:'Find candidate researchers',body:'Lexical and semantic searches find relevant papers. Their authors become candidates, and the research graph supplies publication and collaboration context.',tag:'Lexical + dense retrieval'},
 {number:'04',label:'Rank',title:'Put the strongest evidence first',body:'The trained ranker scores candidates using research relevance and historical features. Grounding checks attach publication-backed claims to results.',tag:'Trained ranker · evidence checks'},
 {number:'05',label:'Explore',title:'Make every match inspectable',body:'Search returns ranked researchers with papers and provenance. Profiles, collaboration-path questions, and session shortlists let you investigate the evidence.',tag:'Results · profiles · assistant'},
];

export function PipelineStory({stats}:{stats:{papers:number;authors:number}|null}){
 const [active,setActive]=useState(0);const current=stages[active];
 return <section className="pipeline-section" id="how-it-works" aria-labelledby="pipeline-title">
  <div className="section-kicker"><span className="kicker-mark"><Icon name="graph" size={15}/></span> UNDER THE HOOD <span className="kicker-line"/></div>
  <div className="pipeline-heading"><div><h2 id="pipeline-title">From paper to <em>the right person.</em></h2><p>ScholarGraph follows a real research retrieval and ranking pipeline. Explore what happens at each step.</p></div><span className="pipeline-version">THE SCHOLARGRAPH METHOD <b>01—05</b></span></div>
  <div className="pipeline-board">
   <div className="pipeline-visual" aria-label="Animated illustration of the research discovery pipeline">
    <div className="visual-topline"><span><i/> PIPELINE OVERVIEW</span><span>{stats?`${stats.papers.toLocaleString()} PAPERS · ${stats.authors.toLocaleString()} AUTHORS`:'DBLP RESEARCH CORPUS'}</span></div>
    <svg className="flow-lines" viewBox="0 0 900 390" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="flow" x1="0" x2="1"><stop stopColor="#8f8af7"/><stop offset=".55" stopColor="#a7e86d"/><stop offset="1" stopColor="#77d9cf"/></linearGradient></defs><path className="flow-base" d="M90 206 C220 206 211 112 343 112 S460 292 558 206 697 206 810 145"/><path className="flow-light" d="M90 206 C220 206 211 112 343 112 S460 292 558 206 697 206 810 145"/><circle className="flow-particle p1" r="5"><animateMotion dur="6s" repeatCount="indefinite" path="M90 206 C220 206 211 112 343 112 S460 292 558 206 697 206 810 145"/></circle><circle className="flow-particle p2" r="3"><animateMotion dur="6s" begin="-2s" repeatCount="indefinite" path="M90 206 C220 206 211 112 343 112 S460 292 558 206 697 206 810 145"/></circle></svg>
    <div className="pipeline-nodes">{stages.map((step,index)=><button className={`pipeline-node node-${index} ${active===index?'is-active':''}`} key={step.number} onClick={()=>setActive(index)} aria-pressed={active===index} aria-label={`Step ${step.number}: ${step.label}`}><span className="node-halo"/><span className="node-glyph">{index===0?<span className="data-stack"><i/><i/><i/></span>:index===1?<Icon name="graph" size={21}/>:index===2?<Icon name="search" size={20}/>:index===3?<span className="scout-mini" aria-hidden="true"><i/><b/><em/></span>:<Icon name="check" size={20}/>}</span><span className="node-number">{step.number}</span><span className="node-name">{step.label}</span>{index<4&&<span className="node-link"/>}</button>)}</div>
    <div className="pipeline-floor"><span>PUBLICATION SIGNALS</span><span className="floor-track"><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/><i/></span><span>GROUNDED RESULTS</span></div>
    <div className="scout-card"><div className="scout-face" aria-hidden="true"><i className="scout-antenna"/><i className="scout-eye left"/><i className="scout-eye right"/><i className="scout-mouth"/></div><div><small>MEET SCOUT</small><p>“I show you <b>why</b> a match made the list.”</p></div><span className="scout-spark">✦</span></div>
    <span className="diagram-caption">A visual guide to the pipeline · not a live ingestion monitor</span>
   </div>
   <div className="pipeline-detail"><div className="detail-counter">{current.number}<span> / 05</span></div><div className="detail-content" key={current.number}><span className="detail-label">{current.label.toUpperCase()} THE GRAPH</span><h3>{current.title}</h3><p>{current.body}</p><div className="detail-tag"><Icon name="check" size={14}/>{current.tag}</div></div><div className="pipeline-tabs" role="tablist" aria-label="Pipeline steps">{stages.map((step,index)=><button key={step.number} role="tab" aria-selected={active===index} className={active===index?'selected':''} onClick={()=>setActive(index)}><span>{step.number}</span>{step.label}<i/></button>)}</div>
   </div>
  </div>
 </section>
}
