#!/usr/bin/env python3
"""Prepare a diagnostic-only blinded pilot. Does not alter production artifacts."""
import csv,hashlib,json,random,sqlite3,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.db import connect
from hiresense.evaluation.split import load_queries,assert_no_leakage
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex,tokens
from hiresense.ranking.scoring import score_model

ROOT=Path('data/research/results'); rows=json.loads((ROOT/'phase5a-loss-attribution.json').read_text())['rows']; labels={q.query_id:q for q in load_queries('data/processed/lean-v1/validation/labels.jsonl')}
def hashkey(x):return hashlib.sha256(('phase5b-v1:'+x['query_id']).encode()).hexdigest()
def has_sources(row):return any(v['archive_exact_record'] for v in row['no_history']) and any(1024<min(y['best_dense_paper_rank'],y['best_bm25_paper_rank'] or 10**9)<=4096 for y in row['source_miss'])
eligible=sorted((r for r in rows if has_sources(r)),key=hashkey);five=eligible[:5];other=sorted((r for r in rows if r not in five),key=hashkey)[:5];selected=five+other
root=Path('data/processed/lean-v1/validation');db=connect(root/'graph.sqlite3');qs=[labels[x['query_id']] for x in selected];assert_no_leakage(db,qs,[],2023);model=json.loads(Path('models/hybrid_ranker.json').read_text());engine=SearchIndex(db,root/'index',LocalEncoder(),**model['retrieval']);src=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
private=[];blind=[];manifest=[]
try:
 for number,(row,q) in enumerate(zip(selected,qs),1):
  pid=f'P{number:02d}';rng=random.Random(314159+number);ctx=engine.candidate_context(q.text);candidate=sorted(ctx['fused'],key=lambda a:(-ctx['fused'][a],a))[:800];data=engine.assemble(q.text,candidate,ctx);scores=score_model(data['features'],model);ranked=[candidate[i] for i in sorted(range(len(candidate)),key=lambda i:(-float(scores[i]),candidate[i]))];chosen={}
  def pick(name,items,n):
   available=sorted(set(items)-set(chosen));rng.shuffle(available)
   for a in available[:n]:chosen[a]=name
  pick('A_frozen_model_top10',ranked[:10],10)
  pick('B_frozen_model_11_800',ranked[10:],2)
  # The strong-evidence rule is intentionally a screening heuristic, not a grade.
  terms=tokens(q.text)
  apparent=[a for a in ranked[100:] if any(len(terms & engine.title_tokens[p])/max(1,len(terms))>=.3 for p in engine.author_papers[a])]
  pick('E_lower_ranked_apparent_evidence',apparent,2)
  engine.paper_limit=4096;deep=engine.candidate_context(q.text);deep_candidates=set(sorted(deep['fused'],key=lambda a:(-deep['fused'][a],a))[:800]);engine.paper_limit=1024
  recovered=[a['author_id'] for a in row['source_miss'] if 1024<min(a['best_dense_paper_rank'],a['best_bm25_paper_rank'] or 10**9)<=4096 and a['author_id'] not in deep_candidates and a['author_id'] not in candidate]
  pick('C_deeper_source_not_800',recovered,2)
  archive={a['author_id']:a['archive_exact_record'] for a in row['no_history'] if a['archive_exact_record']};pick('D_archive_only_exact_key',archive,2)
  all_graph=[a for a in chosen if a in engine.author_papers];evidence_ctx={**ctx,'fused':{**ctx['fused'],**{a:ctx['fused'].get(a,0.0) for a in all_graph}}};evidence=engine.assemble(q.text,all_graph,evidence_ctx)['evidence'];packets=[]
  for author,stratum in chosen.items():
   if stratum.startswith('D_'):
    a=archive[author];paper={'paper_id':a['id'],'title':a['title'],'year':a['year'],'source':'dblp','venue':None};name=src.execute('select canonical_name from authors where id=?',(author,)).fetchone()[0]; papers=[paper]
   else:
    name=engine.authors[author];papers=[]
    for ix in evidence[author]:
     p=engine.papers[ix];venue=db.execute('select venue from papers where id=?',(p['id'],)).fetchone()[0];papers.append({'paper_id':p['id'],'title':p['title'],'year':p['year'],'venue':venue,'source':'dblp'})
   if not papers or any(not p['year'] or p['year']>2023 for p in papers):raise ValueError('Invalid temporal evidence')
   packets.append({'query_id':pid,'query':q.text,'cutoff_year':2023,'person_id':author,'author_name':name,'evidence':json.dumps(papers,ensure_ascii=False)})
   private.append({'query_id':pid,'source_query_id':q.query_id,'person_id':author,'stratum':stratum,'frozen_model_rank':ranked.index(author)+1 if author in ranked else '', 'proxy_future_author':int(author in q.relevant_author_ids),'evidence_year_cutoff':2023})
  rng.shuffle(packets)
  for packet in packets:
   for slot in (1,2):blind.append({**packet,'reviewer_slot':slot,'grade_0_to_3':'','reviewer':'','notes':''})
  manifest.append({'query_id':pid,'source_query_id':q.query_id,'sampling_group':'C_and_D_available' if row in five else 'hash_sample_remaining','stratum_counts':{s:sum(x==s for x in chosen.values()) for s in sorted(set(chosen.values()))},'recovery_eligibility_C':len(recovered),'archive_eligibility_D':len(archive)})
  print(pid,len(packets),'c',len(recovered),'d',len(archive),flush=True)
finally:engine.close();db.close();src.close()
with (ROOT/'phase5b-excluded-author-sample.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(private[0]));w.writeheader();w.writerows(private)
# Merge original review sheet unchanged as a separate cohort. Do not overwrite it.
original=list(csv.DictReader(open('data/research/experiments/phase3-review-template.csv',encoding='utf-8',newline='')))
for r in original:r.update({'cutoff_year':2024,'reviewer_slot':1})
fields=['query_id','query','cutoff_year','person_id','author_name','evidence','reviewer_slot','grade_0_to_3','reviewer','notes']
with (ROOT/'phase5b-blinded-review.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(original);w.writerows(blind)
Path('/tmp/phase5b-sampling-manifest.json').write_text(json.dumps({'seed':314159,'query_hash_salt':'phase5b-v1:','selection':'five hash-ordered queries with C and D opportunities, then five hash-ordered remaining queries','pilot':manifest,'pilot_unique_pairs':len(private),'pilot_review_rows':len(blind),'original_rows':len(original)},indent=2))
