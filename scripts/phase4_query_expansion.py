#!/usr/bin/env python3
"""Development-only bounded acronym expansion retrieval pilot."""
import json,re,sys,time,resource
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage,load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex

MAPPING={'GNN':'graph neural network','LLM':'large language model','NLP':'natural language processing','IR':'information retrieval','KG':'knowledge graph','RL':'reinforcement learning','CNN':'convolutional neural network','RNN':'recurrent neural network','DBMS':'database management system','SQL':'structured query language','GPU':'graphics processing unit','DP':'differential privacy'}
def expand(text):
 terms=[]
 for key,val in MAPPING.items():
  if re.search(r'(?<![A-Za-z0-9])'+key+r's?(?![A-Za-z0-9])',text):terms.append(val)
 return text+' '+' '.join(terms) if terms else text
out=Path('resources/results/phase4-query-expansion-pilot.json')
if out.exists():raise ValueError('Use new report')
root=Path('data/processed/lean-v1/validation');queries=load_queries(root/'labels.jsonl');db=connect(root/'graph.sqlite3');assert_no_leakage(db,queries,[],2023);model=json.load(open('models/hybrid_ranker.json'));index=SearchIndex(db,root/'index',LocalEncoder(),**model['retrieval']);base=[];alt=[];times=[];base_times=[];changed=0;start=time.monotonic()
try:
 for q in queries:
  t=time.monotonic();ctx=index.candidate_context(q.text);order=sorted(ctx['fused'],key=lambda a:(-ctx['fused'][a],a))[:800];base_times.append((time.monotonic()-t)*1000);query=expand(q.text);t=time.monotonic()
  if query!=q.text:
   changed+=1;extra=index.candidate_context(query);other=sorted(extra['fused'],key=lambda a:(-extra['fused'][a],a))[:800];fused={}
   for weight,items in ((1.,order),(.25,other)):
    for rank,a in enumerate(items,1):fused[a]=fused.get(a,0)+weight/(60+rank)
   candidate=sorted(fused,key=lambda a:(-fused[a],a))[:800]
  else:candidate=order
  times.append(base_times[-1]+(time.monotonic()-t)*1000)
  relevant=set(q.relevant_author_ids);known={a for a in relevant if index.author_papers.get(a)}
  def evaluate(ids):
   context=dict(ctx,fused=dict(ctx['fused']))
   for a in ids:context['fused'].setdefault(a,0.)
   found=index.assemble(q.text,ids,context);scores=score_model(found['features'],model);ranked=[ids[i] for i in np.lexsort((np.asarray(ids),-scores))];hits=relevant&set(ids)
   return {'ndcg_at_10':ranking_metrics(ranked[:10],relevant)['ndcg_at_10'],'mrr_at_10':ranking_metrics(ranked[:10],relevant)['mrr_at_10'],'hit_at_10':ranking_metrics(ranked[:10],relevant)['hit_at_10'],'candidate_relevant':len(hits),'known':len(known),'all':len(relevant),'query_hit':int(bool(hits)),'oracle':ranking_metrics(sorted(hits),relevant)['ndcg_at_10']}
  base.append(evaluate(order));alt.append(evaluate(candidate))
 def summarize(rows):
  return {**{k:float(np.mean([r[k] for r in rows])) for k in ('ndcg_at_10','mrr_at_10','hit_at_10','query_hit','oracle')},'candidate_recall_known':sum(r['candidate_relevant'] for r in rows)/sum(r['known'] for r in rows),'candidate_recall_all':sum(r['candidate_relevant'] for r in rows)/sum(r['all'] for r in rows)}
 rng=np.random.default_rng(42);sample=rng.integers(0,len(queries),(5000,len(queries)));d=np.array([a['ndcg_at_10']-b['ndcg_at_10'] for a,b in zip(alt,base)])
 report={'scope':'Previously inspected 2024 development cohort; automatic future authorship proxy, no human judgments. Existing 800 author cap; query expansion adds second retrieval route, baseline features used for reranker with zero prior for new authors.','command':sys.argv,'labels_sha256':digest_file(root/'labels.jsonl'),'model_sha256':digest_file('models/hybrid_ranker.json'),'mapping':MAPPING,'queries':len(queries),'queries_expanded':changed,'baseline':summarize(base),'expansion':summarize(alt),'paired_ndcg_delta':float(d.mean()),'paired_95pct':np.quantile(d[sample].mean(axis=1),[.025,.975]).tolist(),'retrieval_latency_ms':{'baseline_p50':float(np.percentile(base_times,50)),'baseline_p95':float(np.percentile(base_times,95)),'expansion_p50':float(np.percentile(times,50)),'expansion_p95':float(np.percentile(times,95))},'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'elapsed_seconds':round(time.monotonic()-start,2),'latency_scope':'Query encoding and source retrieval; excludes feature assembly, ranker, grounding and HTTP.'}
 write_json(out,report);print(json.dumps(report,indent=2))
finally:index.close();db.close()
