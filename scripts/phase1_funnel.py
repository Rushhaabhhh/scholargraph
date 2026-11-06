import argparse,hashlib,json,resource,statistics,sys,time
import numpy as np
from pathlib import Path
from hiresense.data.artifacts import digest_file
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage,load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex

parser=argparse.ArgumentParser(description='Trace source and author candidates on the fixed development cohort')
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
if args.out.exists(): raise ValueError('Use a fresh report path')
window=Path('data/processed/lean-v1/validation'); meta=json.loads((window/'manifest.json').read_text());labels=window/'labels.jsonl'
assert digest_file(labels)==meta['labels_sha256']; queries=load_queries(labels);db=connect(window/'graph.sqlite3');assert_no_leakage(db,queries,[],meta['cutoff']);model=json.load(open('models/hybrid_ranker.json'))
enc=LocalEncoder(); index=SearchIndex(db,window/'index',enc,**model['retrieval']); times=[]; rows=[]
for q in queries:
 t=time.perf_counter();context=index.candidate_context(q.text);sim=context['similarities']; n=min(index.paper_limit,len(index.papers));dense=set(np.argpartition(-sim,n-1)[:n].tolist()) if n else set();lex=set(context['lexical_scores']);papers=lex|dense
 discovered={a for p in papers for a in index.paper_authors[p]}; ordered=sorted(context['fused'],key=lambda a:(-context['fused'][a],a))[:800]; res=index.assemble(q.text,ordered,context); values=score_model(res['features'],model);ranked=[ordered[i] for i in sorted(range(len(ordered)),key=lambda i:(-float(values[i]),ordered[i]))]; timings=(time.perf_counter()-t)*1000; times.append(timings)
 truth=set(q.relevant_author_ids);known={a for a in truth if index.author_papers.get(a)}; reached=truth&discovered; candidates=truth&set(ordered);top=truth&set(ranked[:10]); relevant_papers={p for a in known for p in index.author_papers[a]};
 row={'query_id':q.query_id,'total':len(truth),'known':len(known),'source_reachable':len(reached),'candidate_100':len(truth&set(ordered[:100])),'candidate_400':len(truth&set(ordered[:400])),'candidate_800':len(candidates),'top10':len(top),'historical_papers':len(relevant_papers),'historical_papers_retrieved':len(relevant_papers&papers),'lexical_papers':len(lex),'dense_papers':len(dense),'unique_source_papers':len(papers),'retrieved_unique_authors':len(discovered),'oracle_all':ranking_metrics(sorted(candidates),truth)['ndcg_at_10'],'oracle_known':ranking_metrics(sorted(candidates),known)['ndcg_at_10'],'ranked_all':ranking_metrics(ranked[:10],truth),'stage_ids':{'no_history':sorted(truth-known),'source_miss':sorted(known-reached),'aggregation_miss':sorted(reached-candidates),'candidate_not_top10':sorted(candidates-top)}}
 assert candidates<=reached<=known<=truth;rows.append(row)
 if len(rows)%25==0:print('processed',len(rows),flush=True)
s=lambda key:sum(x[key] for x in rows); total=s('total');known=s('known');
report={'scope':'Previously inspected 2024 validation; future authorship proxy, not human relevance. Historical author papers are not independently relevance-labelled. Source retrieval is union of BM25 and dense top 1024 papers per channel. No model retraining.', 'graph_cutoff':meta['cutoff'],'labels_sha256':digest_file(labels),'index_content_sha256':index.manifest['content_sha256'],'model_sha256':digest_file('models/hybrid_ranker.json'),'query_count':len(rows),'model_retrieval':model['retrieval'],'counts':{k:s(k) for k in ('total','known','source_reachable','candidate_100','candidate_400','candidate_800','top10','historical_papers','historical_papers_retrieved')},'historical_coverage':known/total,'author_source_recall_all':s('source_reachable')/total,'author_source_recall_known':s('source_reachable')/known,'paper_recall':s('historical_papers_retrieved')/s('historical_papers'),'candidate_recall':{str(k):{'all':s('candidate_'+str(k))/total,'known':s('candidate_'+str(k))/known} for k in (100,400,800)},'query_hit_at_800':sum(x['candidate_800']>0 for x in rows)/len(rows),'query_hit_at_800_among_known_queries':sum(x['candidate_800']>0 for x in rows)/sum(x['known']>0 for x in rows),'oracle_ndcg10_all':statistics.fmean(x['oracle_all'] for x in rows),'oracle_ndcg10_known':statistics.fmean(x['oracle_known'] for x in rows),'oracle_mrr10_all':sum(x['candidate_800']>0 for x in rows)/len(rows),'oracle_mrr10_known_queries':sum(x['candidate_800']>0 for x in rows)/sum(x['known']>0 for x in rows),'ndcg10':statistics.fmean(x['ranked_all']['ndcg_at_10'] for x in rows),'mrr10':statistics.fmean(x['ranked_all']['mrr_at_10'] for x in rows),'latency_ms':{'p50':float(np.percentile(times,50)),'p95':float(np.percentile(times,95)),'scope':'Sequential query encoding, candidate retrieval, feature assembly, model; no HTTP or grounding'},'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'rows':rows}
args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2),flush=True);index.close();db.close()
