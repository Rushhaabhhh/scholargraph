'use client';
import {FormEvent,useCallback,useEffect,useRef,useState} from 'react';
import {AppLayout} from './AppLayout';
import {Brand} from './Brand';
import {getSession} from '../lib/session';
import {ExpertCard} from './ExpertCard';
import {EvidenceGraph} from './EvidenceGraph';
import {PipelineStory} from './PipelineStory';
import {AssistantDialog,type ChatTurn} from './AssistantDialog';
import {Icon} from './Icon';
import {api,ApiError,json,requestId} from '../lib/api';
import type {ChatResponse,Expert,Memory,SearchResponse} from '../lib/types';
type Health={status:'ok'|'degraded';papers:number;authors:number;model_version:string;query_provider:string};
const examples=['Graph neural networks','Information retrieval','Computer vision'];

export function Workspace(){
 const [session,setSession]=useState('');const [memory,setMemory]=useState<Memory|null>(null);const [ready,setReady]=useState(false);
 const [query,setQuery]=useState('');const [recency,setRecency]=useState<'any'|'recent'>('any');const [sinceYear,setSinceYear]=useState('');const [health,setHealth]=useState<Health|null>(null);const [assistantOpen,setAssistantOpen]=useState(false);
 const [searched,setSearched]=useState('');const [results,setResults]=useState<Expert[]>([]);const [searchInfo,setSearchInfo]=useState<SearchResponse|null>(null);
 const [searching,setSearching]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [chatError,setChatError]=useState('');const [turns,setTurns]=useState<ChatTurn[]>([]);const [message,setMessage]=useState('');
 const searchAbort=useRef<AbortController|null>(null);const searchSeq=useRef(0);const apiOnline=health?.status==='ok';

 useEffect(()=>{
  let active=true, initialized=false, initializing=false;
  async function connect(){
   if(initialized||initializing)return;
   initializing=true;
   try{
    const info=await getSession();if(!active)return;
    initialized=true;setSession(info.session_id);setMemory(info.memory);setReady(true);setError('');
    const asked=new URLSearchParams(window.location.search).get('ask');
    if(asked){setMessage(`Show profile ${asked}`);setAssistantOpen(true);window.history.replaceState({},'', '/')}
    try{
     const cached=JSON.parse(sessionStorage.getItem('scholargraph-results')||sessionStorage.getItem('hiresense-results')||'null') as SearchResponse|null;
     if(cached){setQuery(cached.query);setSearched(cached.query);setResults(cached.results);setSearchInfo(cached);setRecency(cached.understanding.intent.recency_preference);setSinceYear(cached.effective_filters.since_year?String(cached.effective_filters.since_year):'')}
    }catch{sessionStorage.removeItem('scholargraph-results');sessionStorage.removeItem('hiresense-results')}
   }catch(e){if(active){setError((e as Error).message);setReady(true)}}finally{initializing=false}
  }
  const refresh=()=>{api<Health>('/health').then(value=>{if(active)setHealth(value)}).catch(()=>{if(active)setHealth(null)});void connect()};
  refresh();const timer=window.setInterval(refresh,5000);
  return()=>{active=false;window.clearInterval(timer);searchAbort.current?.abort()};
 },[]);

 async function currentMemory(){const m=await api<Memory>(`/sessions/${session}/memory`);setMemory(m);return m}
 async function mutate<T extends {memory:Memory}>(path:string,method:string,body:Record<string,unknown>,signal?:AbortSignal):Promise<T>{const m=await currentMemory();const payload={...body,expected_version:m.version,request_id:requestId()};try{return await api<T>(path,json(method,payload,signal))}catch(e){if(e instanceof ApiError&&e.status===0)return api<T>(path,json(method,payload,signal));if(e instanceof ApiError&&e.status===409){await currentMemory();throw new Error('Your session changed during this request. Please try again.')}throw e}}
 async function search(value:string,filters:{recency?:'any'|'recent';sinceYear?:string}={}){
  const q=value.trim();const appliedRecency=filters.recency??recency;const appliedYear=filters.sinceYear??sinceYear;
  if(appliedYear&&(!Number.isInteger(Number(appliedYear))||Number(appliedYear)<1||Number(appliedYear)>9999)){setError('Enter a year from 1 to 9999.');return}
  if(!q||!session)return;
  searchAbort.current?.abort();const controller=new AbortController();searchAbort.current=controller;const seq=++searchSeq.current;setQuery(q);setSearching(true);setError('');
  try{
   let data:SearchResponse|undefined;
   for(let attempt=0;attempt<2;attempt++){
    const m=await currentMemory();if(seq!==searchSeq.current||controller.signal.aborted)return;
    const payload={query:q,limit:10,recency_preference:appliedRecency,since_year:appliedYear?Number(appliedYear):null,session_id:session,expected_version:m.version,request_id:requestId()};
    try{data=await api<SearchResponse>('/search',json('POST',payload,controller.signal));break}
    catch(e){if(e instanceof ApiError&&e.status===409&&attempt===0)continue;throw e}
   }
   if(!data||seq!==searchSeq.current||controller.signal.aborted)return;
   setRecency(appliedRecency);setSinceYear(appliedYear);setSearched(q);setResults(data.results);setSearchInfo(data);sessionStorage.setItem('scholargraph-results',JSON.stringify(data));if(data.memory)setMemory(data.memory);document.getElementById('discovery-results')?.scrollIntoView({behavior:'smooth',block:'start'});
  }catch(e){if(seq===searchSeq.current&&(e as Error).name!=='AbortError')setError(e instanceof ApiError&&e.status===409?'Your session changed while searching. Please search again.':(e as Error).message)}
  finally{if(seq===searchSeq.current)setSearching(false)}
 }
 async function decide(id:number,decision:'shortlist'|'reject'|'clear'){if(!session)return;setBusy(true);setError('');try{const data=await mutate<{memory:Memory}>(`/sessions/${session}/decisions/${id}`,'PUT',{decision});setMemory(data.memory)}catch(e){await currentMemory().catch(()=>{});setError((e as Error).message)}finally{setBusy(false)}}
 async function clearMemory(){setBusy(true);setChatError('');try{const data=await mutate<{memory:Memory}>(`/sessions/${session}/memory`,'DELETE',{});setMemory(data.memory);setTurns([]);setSearched('');setQuery('');setResults([]);setSearchInfo(null);setRecency('any');setSinceYear('');sessionStorage.removeItem('scholargraph-results');sessionStorage.removeItem('hiresense-results')}catch(e){setChatError((e as Error).message)}finally{setBusy(false)}}
 async function send(e:FormEvent){e.preventDefault();const text=message.trim();if(!text||!session||busy||searching)return;setBusy(true);setChatError('');setMessage('');setTurns(t=>[...t,{role:'user',text}]);try{const data=await mutate<ChatResponse>(`/sessions/${session}/messages`,'POST',{message:text});setMemory(data.memory);setTurns(t=>[...t,{role:'assistant',text:data.message,response:data}]);if(data.tool_calls.some(call=>call.tool==='search_experts'&&call.outcome==='success')){setResults(data.results);const searchedQuery=data.query||data.memory.last_query||text;setQuery(searchedQuery);setSearched(searchedQuery);if(data.understanding&&data.effective_filters){const refreshed:SearchResponse={query:searchedQuery,retrieval_query:data.retrieval_query||searchedQuery,results:data.results,memory:data.memory,understanding:data.understanding,effective_filters:data.effective_filters};setSearchInfo(refreshed);setRecency(data.understanding.intent.recency_preference);setSinceYear(data.effective_filters.since_year?String(data.effective_filters.since_year):'');sessionStorage.setItem('scholargraph-results',JSON.stringify(refreshed))}}}catch(e){setTurns(t=>t.slice(0,-1));setChatError((e as Error).message);setMessage(text)}finally{setBusy(false)}}
 const closeAssistant=useCallback(()=>setAssistantOpen(false),[]);const showSearchResults=useCallback(()=>{setAssistantOpen(false);window.setTimeout(()=>document.getElementById('discovery-results')?.scrollIntoView({behavior:'smooth',block:'start'}),80)},[]);

 const visible=results.filter(r=>!memory?.rejected_person_ids.includes(r.person_id));const filtersValid=!sinceYear||(Number.isInteger(Number(sinceYear))&&Number(sinceYear)>=1&&Number(sinceYear)<=9999);
 return <AppLayout><div className="home-page" id="top">
  <section className="hero-section" aria-labelledby="hero-title"><div className="hero-copy"><div className="hero-badge"><span className="live-dot"/>{apiOnline?'RESEARCH GRAPH ONLINE':'RESEARCH INTELLIGENCE WORKSPACE'}</div><h1 id="hero-title">Find the minds<br/>behind the <span>research.</span></h1><p className="hero-description">ScholarGraph connects research questions to the people, papers, and collaboration evidence that make a match worth your time.</p><div className="hero-actions"><a className="button-primary" href="#search">Explore researchers <Icon name="arrow" size={17}/></a><a className="button-quiet" href="#how-it-works">See how it works <span>↓</span></a></div><div className="hero-proof"><span><Icon name="check" size={14}/>Publication-backed matches</span><span><Icon name="check" size={14}/>Every connection has a source</span></div></div>
   <div className="hero-art" aria-label="Conceptual illustration of researchers linked through sourced papers"><div className="hero-art-grid"/><svg viewBox="0 0 640 500" className="hero-network" aria-hidden="true"><defs><linearGradient id="heroLine" x1="0" x2="1"><stop stopColor="#8c81f4"/><stop offset=".55" stopColor="#b0ef70"/><stop offset="1" stopColor="#68ded2"/></linearGradient><filter id="softGlow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><g className="hero-links"><path d="M102 253 235 155 365 197 518 119M102 253 247 344 365 197M247 344l186 71 85-296M235 155l198 260M102 253 433 415"/><path d="M235 155 518 119M365 197 433 415"/></g><g className="hero-dots"><circle cx="102" cy="253" r="7"/><circle cx="235" cy="155" r="5"/><circle cx="365" cy="197" r="11"/><circle cx="518" cy="119" r="6"/><circle cx="247" cy="344" r="8"/><circle cx="433" cy="415" r="6"/></g><circle className="hero-pulse" cx="365" cy="197" r="31"/></svg><div className="hero-floating-card card-paper"><span className="float-icon"><Icon name="bookmark" size={15}/></span><span><small>SOURCED PUBLICATION</small><b>Paper record<br/>with topic evidence</b></span><i className="mini-signal"/></div><div className="hero-floating-card card-researcher"><span className="float-avatar"><Icon name="graph" size={14}/></span><span><small>RESEARCHER NODE</small><b>Matched from publications</b></span><span className="match-mark">↗</span></div><div className="hero-center-node"><div><Icon name="graph" size={24}/></div><span>RESEARCH<br/>CONTEXT</span></div><div className="art-caption"><span>CONCEPTUAL VIEW · CONNECTED EVIDENCE</span><span>PEOPLE · PAPERS · IDEAS</span></div><div className="art-index">SG / 01</div></div>
   <div className="hero-statline"><div><strong>{health?health.papers.toLocaleString():'—'}</strong><span>RESEARCH PAPERS</span></div><div><strong>{health?health.authors.toLocaleString():'—'}</strong><span>AUTHOR RECORDS</span></div><div><strong>{health?.model_version||'LOCAL'}</strong><span>RANKING ENGINE</span></div><span className="stat-footnote">{apiOnline?'Live from the configured research corpus':'Counts shown when the backend is available'}</span></div>
  </section>
  <PipelineStory stats={health?{papers:health.papers,authors:health.authors}:null}/>
  <section className="search-section" id="search" aria-labelledby="search-title"><div className="search-heading"><div><div className="section-kicker"><span className="kicker-mark"><Icon name="search" size={15}/></span> START YOUR DISCOVERY <span className="kicker-line"/></div><h2 id="search-title">What expertise are you <em>looking for?</em></h2><p>Describe the problem, method, or field. We’ll search the graph and show the publication trail.</p></div><span className={`backend-pill ${apiOnline?'is-online':'is-offline'}`}><i/>{apiOnline?'BACKEND READY':'BACKEND UNAVAILABLE'}</span></div>
   <form className={`search-composer ${searching?'is-searching':''}`} onSubmit={e=>{e.preventDefault();search(query)}}><label htmlFor="query">RESEARCH QUESTION OR TOPIC</label><div className="search-input-row"><span className="composer-icon"><Icon name="search" size={21}/></span><input id="query" value={query} onChange={e=>setQuery(e.target.value)} placeholder="e.g. researchers working on graph neural networks for drug discovery" maxLength={4000}/>{query&&<button type="button" className="clear-query" aria-label="Clear query" onClick={()=>setQuery('')}><Icon name="close" size={16}/></button>}<button className="search-submit" disabled={!ready||!session||busy||!query.trim()||!filtersValid}>{searching?<><span className="button-spinner"/>Searching</>:<>Find researchers <Icon name="arrow" size={16}/></>}</button></div><div className="filter-row"><label>PUBLICATION ACTIVITY<select aria-label="Publication activity" value={recency} onChange={e=>setRecency(e.target.value as 'any'|'recent')}><option value="any">Any time</option><option value="recent">Recent work</option></select></label><label>FROM YEAR<input aria-label="Since year" type="number" min="1" max="9999" placeholder="Any year" value={sinceYear} onChange={e=>setSinceYear(e.target.value.slice(0,4))}/></label>{sinceYear&&!filtersValid&&<span className="filter-error" role="alert">Enter a year from 1 to 9999.</span>}{(recency==='recent'||sinceYear)&&<button className="clear-filters" type="button" onClick={()=>{setRecency('any');setSinceYear('');if(query.trim()&&session)search(query,{recency:'any',sinceYear:''})}}>Reset filters</button>}<div className="query-examples"><span>TRY:</span>{examples.map(x=><button type="button" key={x} disabled={!session||busy} onClick={()=>{setQuery(x);search(x)}}>{x}</button>)}</div></div></form>
   {error&&<div className="error-banner" role="alert">{error} {session?<button onClick={()=>search(query)}>Retry search</button>:<button onClick={()=>window.location.reload()}>Retry connection</button>}</div>}
   <div className="results-heading" id="discovery-results"><div><span className="eyebrow">EVIDENCE-LED DISCOVERY</span><h3>{searched?'Researchers for your question':'Your results will appear here'}{searched&&<span className="count">{String(visible.length).padStart(2,'0')}</span>}</h3></div>{searched&&searchInfo&&<div className="results-meta"><span>{searchInfo.understanding.intent.topics.join(' · ')||searchInfo.query}</span><small>GRAPH CUTOFF {searchInfo.effective_filters.graph_cutoff_year} · {searchInfo.understanding.provider.replace('_',' ').toUpperCase()}</small></div>}</div>
   {searched&&searchInfo&&<div className="search-summary"><span>QUERY</span><b>{searchInfo.query}</b><i/><span>SEARCH INTENT</span><b>{searchInfo.understanding.intent.topics.join(' · ')||'No separate topic extraction'}</b>{searchInfo.effective_filters.since_year&&<em>Since {searchInfo.effective_filters.since_year}</em>}{searchInfo.understanding.intent.recency_preference==='recent'&&<em>Recent work</em>}</div>}
   {searching?<div className="skeleton-list" role="status" aria-label="Searching the research graph"><div/><div/><div/></div>:!searched?<div className="results-placeholder"><div className="placeholder-orbit"><span/><i/><b/></div><div><strong>One thoughtful query can open a whole field.</strong><p>Start with a research challenge. Your results will include people, the work they published, and the connections behind the ranking.</p></div><span className="placeholder-index">READY WHEN YOU ARE · 02</span></div>:visible.length===0?<div className="state"><h3>No researchers found for this view.</h3><p>Try a broader phrase, change the year filter, or restore a previously rejected researcher from your shortlist.</p><a className="text-link" href="/shortlist">Review shortlist and rejected people →</a></div>:<><div className="result-list">{visible.map(expert=><ExpertCard key={expert.person_id} expert={expert} index={results.findIndex(result=>result.person_id===expert.person_id)} memory={memory} busy={busy||searching} onDecision={decide} onAsk={(expert,index)=>{setMessage(`Show profile #${index+1}`);setAssistantOpen(true)}}/>)}</div><p className="results-footnote">Scores order retrieved matches; they are model ranking scores, not probabilities or hiring accuracy. Inspect the sourced evidence before making a decision.</p><EvidenceGraph experts={visible}/></>}
  </section>
  <footer className="site-footer"><Brand/><span>Research intelligence, built on traceable work.</span><a href="#top">Back to top ↑</a></footer>
 </div>
 <button id="assistant-launcher" className={`assistant-launcher ${assistantOpen?'opened':''}`} aria-label={assistantOpen?'Close Research Assistant':'Open Research Assistant'} aria-expanded={assistantOpen} onClick={()=>setAssistantOpen(v=>!v)}><span className="launcher-orbit"><i/><b/></span><span>{assistantOpen?'Close':'Ask Scholar'}</span>{!assistantOpen&&<span className="launcher-ping"/>}</button>
 <AssistantDialog open={assistantOpen} onClose={closeAssistant} online={apiOnline} session={session} memory={memory} results={results} turns={turns} message={message} busy={busy} searching={searching} error={chatError} onMessageChange={setMessage} onSend={send} onClearMemory={clearMemory} onViewResults={showSearchResults}/>
 </AppLayout>
}
