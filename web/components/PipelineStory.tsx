'use client';
import {useEffect,useRef,useState} from 'react';
import {motion,AnimatePresence,useReducedMotion} from 'motion/react';
import {gsap} from 'gsap';
import {ScrollTrigger} from 'gsap/ScrollTrigger';
const stages=[
 {label:'SOURCE',title:'Start with the work.',body:'Publications, dates and author records form the evidence base. Every discovery begins with a real research record.'},
 {label:'CONNECT',title:'See the connections.',body:'Author identities and coauthorship links bring papers and people together in a sourced research graph.'},
 {label:'RETRIEVE',title:'Find the signal.',body:'Keyword and semantic search find relevant publications and the researchers behind them.'},
 {label:'RANK',title:'Put relevance first.',body:'A trained ranking model orders candidates using research relevance and historical graph features.'},
 {label:'EXPLORE',title:'Follow the evidence.',body:'Inspect supporting publications, open profiles and build a shortlist of people worth knowing.'},
];
export function PipelineStory({stats}:{stats:{papers:number;authors:number}|null}){
 const [active,setActive]=useState(0);const root=useRef<HTMLElement>(null);const reduced=useReducedMotion();
 useEffect(()=>{if(reduced||!root.current)return;gsap.registerPlugin(ScrollTrigger);const ctx=gsap.context(()=>{gsap.fromTo('.method-reveal',{y:45,opacity:0},{y:0,opacity:1,duration:.8,stagger:.14,scrollTrigger:{trigger:root.current,start:'top 80%',once:true}})},root);return()=>ctx.revert()},[reduced]);
 return <section ref={root} className="method-section" id="how-it-works" aria-labelledby="pipeline-title">
  <div className="method-header method-reveal"><span>THE METHOD</span><span>FROM INFORMATION TO INSIGHT</span></div>
  <h2 id="pipeline-title" className="method-title method-reveal">CONNECTIONS<br/><span>WITH CONTEXT.</span></h2>
  <div className="method-grid method-reveal"><div className="method-list" role="tablist" aria-label="Pipeline steps">{stages.map((s,i)=><button key={s.label} role="tab" aria-selected={active===i} onClick={()=>setActive(i)}><span>0{i+1}</span><b>{s.label}</b><i>{active===i?'↗':'+'}</i></button>)}</div><div className="method-detail"><AnimatePresence mode="wait"><motion.div key={active} initial={reduced?false:{opacity:0,y:12}} animate={{opacity:1,y:0}} exit={reduced?undefined:{opacity:0,y:-8}} transition={{duration:.22}}><h3>{stages[active].title}</h3><p>{stages[active].body}</p></motion.div></AnimatePresence><div className="method-detail-bottom"><span>{stats?`${stats.papers.toLocaleString()} PAPERS / ${stats.authors.toLocaleString()} AUTHORS`:'PUBLICATION-BACKED DISCOVERY'}</span><span>↗</span></div></div></div>
 </section>
}
