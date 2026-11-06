import json,time,resource,sys,statistics,sqlite3
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0,'src')
from hiresense.data.artifacts import digest_file
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.phase1_retrieval import aggregate_papers
from hiresense.evaluation.split import load_queries,assert_no_leakage
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex,tokens
root=Path('data/processed/lean-v1/validation');labels=root/'labels.jsonl';meta=json.loads((root/'manifest.json').read_text());qs=load_queries(labels)
assert digest_file(labels)==meta['labels_sha256'];base=json.load(open('resources/results/phase1-baseline-funnel-v1.json'));byid={r['query_id']:r for r in base['rows']}
db=connect(root/'graph.sqlite3');assert_no_leakage(db,qs,[],2023);model=json.load(open('models/hybrid_ranker.json'));index=SearchIndex(db,root/'index',LocalEncoder(),**model['retrieval']); result=[]; depths={str(d):[] for d in (1024,2048,4096)};t0=time.monotonic()
for num,q in enumerate(qs,1):
 truth=set(q.relevant_author_ids); known={a for a in truth if index.author_papers.get(a)};qt=tokens(q.text); vector=index.encoder.encode([q.text])[0]; contexts={}
 for depth in (1024,2048,4096):
  index.paper_limit=depth; t=time.perf_counter();c=index.candidate_context(q.text,vector);order=sorted(c['fused'],key=lambda a:(-c['fused'][a],a));hits=truth&set(order[:800]);papers=set(c['lexical_scores'])|set(np.argpartition(-c['similarities'],depth-1)[:depth].tolist());reached={a for p in papers for a in index.paper_authors[p]};elapsed=(time.perf_counter()-t)*1000
  depths[str(depth)].append({'query_id':q.query_id,'reachable':len(truth&reached),'candidate':len(hits),'hit':int(bool(hits)),'oracle_ndcg':ranking_metrics(sorted(hits),truth)['ndcg_at_10'],'elapsed_ms':elapsed});contexts[depth]=(c,order,papers)
 c,order,papers=contexts[1024];positions={a:i+1 for i,a in enumerate(order)};lex1024=c['lexical_scores']; index.paper_limit=len(index.papers); t=time.perf_counter();lexall=index._lexical(q.text);lexrank={p:i+1 for i,(p,_) in enumerate(lexall)}; sim=c['similarities']; cutoff=order[799] if len(order)>=800 else order[-1]
 def detail(a):
  ps=index.author_papers[a];best=max(ps,key=lambda p:float(sim[p]));lr=min((lexrank[p] for p in ps if p in lexrank),default=None); dense_rank=1+int(np.count_nonzero(sim>sim[best])); best_match=max(ps,key=lambda p:len(qt&index.title_tokens[p])/max(1,len(qt)));strong=ps and max(len(qt&index.title_tokens[p])/max(1,len(qt)) for p in ps)
  return {'author_id':a,'name':index.authors.get(a),'historical_papers_indexed':len(ps),'best_bm25_paper_rank':lr,'best_dense_paper_rank':dense_rank,'best_dense_similarity':float(sim[best]),'best_dense_paper':index.papers[best],'best_token_overlap':strong,'best_overlap_paper':index.papers[best_match],'author_aggregation_rank':positions.get(a),'author_aggregation_score':c['fused'].get(a),'lexical_author_rank':c['lexical_rank'].get(a),'dense_author_rank':c['dense_rank'].get(a),'source_papers':len(set(ps)&papers)}
 row=byid[q.query_id];sm=[detail(a) for a in row['stage_ids']['source_miss']];am=[detail(a) for a in row['stage_ids']['aggregation_miss']];cut=detail(cutoff) if am else None
 result.append({'query_id':q.query_id,'query':q.text,'source_miss':sm,'aggregation_miss':am,'cutoff_candidate':cut})
 if num%25==0:print(num,'elapsed',round(time.monotonic()-t0),flush=True)
index.close();db.close();Path('/tmp/phase5a-retrieval-raw.json').write_text(json.dumps({'rows':result,'depths':depths,'elapsed_seconds':time.monotonic()-t0,'peak_rss_kb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},indent=2));print('done',flush=True)
