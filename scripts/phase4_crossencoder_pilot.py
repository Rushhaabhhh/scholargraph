#!/usr/bin/env python3
"""Bounded cross-encoder fusion pilot on inspected development queries only."""
import json,sys,time,resource
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage,load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.index import SearchIndex

out=Path('resources/results/phase4-crossencoder-pilot.json')
if out.exists():raise ValueError('Use a new pilot report')
window=Path('data/processed/lean-v1/validation');queries=load_queries(window/'labels.jsonl');db=connect(window/'graph.sqlite3');assert_no_leakage(db,queries,[],2023);model=json.loads(Path('models/hybrid_ranker.json').read_text());start=time.monotonic();index=SearchIndex(db,window/'index',LocalEncoder(),**model['retrieval']);cross=CrossEncoder('models/crossencoder',threads=2)
metrics={str(a):[] for a in (0.,.25,.5,.75,1.)};durations=[];cross_durations=[]
try:
 for n,q in enumerate(queries,1):
  t=time.monotonic();found=index.retrieve(q.text);ids=found['author_ids'];values=score_model(found['features'],model);order=sorted(ids,key=lambda a:(-float(values[ids.index(a)]),a));shortlist=order[:30]
  # Exactly one independent comparison per person; only reorder top 30.
  titles=[index.papers[found['evidence'][a][0]]['title'] for a in shortlist];t2=time.monotonic();logits=cross.score(q.text,titles);cross_durations.append((time.monotonic()-t2)*1000)
  cr=sorted(range(len(shortlist)),key=lambda i:(-float(logits[i]),shortlist[i]));cross_rank={shortlist[i]:rank for rank,i in enumerate(cr,1)}
  for alpha in (0.,.25,.5,.75,1.):
   candidate=sorted(shortlist,key=lambda a:(-((1-alpha)/(60+order.index(a)+1)+alpha/(60+cross_rank[a])),a))+order[30:]
   metrics[str(alpha)].append(ranking_metrics(candidate[:10],set(q.relevant_author_ids)))
  durations.append((time.monotonic()-t)*1000)
  if n%25==0:print('pilot',n,'/',len(queries),flush=True)
 rng=np.random.default_rng(42);bootstrap=rng.integers(0,len(queries),size=(5000,len(queries)));summary={}
 for method,rows in metrics.items():
  delta=np.array([a['ndcg_at_10']-b['ndcg_at_10'] for a,b in zip(rows,metrics['0.0'])]);summary[method]={'ndcg_at_10':float(np.mean([r['ndcg_at_10'] for r in rows])),'mrr_at_10':float(np.mean([r['mrr_at_10'] for r in rows])),'hit_at_10':float(np.mean([r['hit_at_10'] for r in rows])),'ndcg_delta_vs_baseline':float(delta.mean()),'paired_interval':np.quantile(delta[bootstrap].mean(axis=1),[.025,.975]).tolist()}
 report={'scope':'Previously inspected 129-query 2024 development cohort, proxy future authorship; not final evidence. Crossencoder scored one paper per top-30 author. Fixed 800 candidates; fusion only reranks top 30.', 'command':sys.argv,'labels_sha256':digest_file(window/'labels.jsonl'),'production_model_sha256':digest_file('models/hybrid_ranker.json'),'crossencoder_manifest_sha256':digest_file('models/crossencoder/manifest.json'),'metrics':summary,'cross_scoring_ms':{'p50':float(np.percentile(cross_durations,50)),'p95':float(np.percentile(cross_durations,95))},'offline_total_ms':{'p50':float(np.percentile(durations,50)),'p95':float(np.percentile(durations,95))},'latency_scope':'Sequential query encoding, retrieval, feature assembly, 30 crossencoder pairs and five scoring comparisons; excludes HTTP and grounding.', 'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'elapsed_seconds':round(time.monotonic()-start,2)}
 write_json(out,report);print(json.dumps(report,indent=2))
finally:index.close();db.close()
