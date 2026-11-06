import json,sqlite3,statistics,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'src')
from hiresense.data.artifacts import digest_file
from hiresense.evaluation.split import load_queries
out=Path('resources/results');root=Path('data/processed/lean-v1/validation')
base=json.load(open(out/'phase1-baseline-funnel-v1.json'));raw=json.load(open('/tmp/phase5a-retrieval-raw.json'));ar=json.load(open('/tmp/phase5a-archive.json'));queries={q.query_id:q for q in load_queries(root/'labels.jsonl')}; old={r['query_id']:r for r in base['rows']}; src=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
rows=[]
for item in raw['rows']:
 row=old[item['query_id']];missing=[]
 for a in row['stage_ids']['no_history']:
  historical=src.execute('select p.id,p.title,p.year from paper_authors pa join papers p on pa.paper_id=p.id where pa.author_id=? and p.year<=2023 limit 1',(a,)).fetchone()
  exact=ar['exact'].get(str(a)); name=ar['same_name_different_key'].get(str(a))
  if historical:category='ingestion_or_snapshot_loss'
  elif exact:category='source_slice_exclusion_exact_identity'
  elif name:category='unresolved_possible_identity_mismatch'
  else:category='no_exact_usable_pre_cutoff_record_in_scanned_archive'
  missing.append({'author_id':a,'classification':category,'archive_exact_record':exact,'same_name_other_key':name,'selected_source_record':historical})
 rows.append({'query_id':item['query_id'],'query':item['query'],'no_history':missing,'source_miss':item['source_miss'],'aggregation_miss':item['aggregation_miss'],'candidate_800_boundary':item['cutoff_candidate']})
from collections import Counter
counts=Counter(a['classification'] for r in rows for a in r['no_history']); sm=[a for r in rows for a in r['source_miss']]; am=[(a,r['candidate_800_boundary']) for r in rows for a in r['aggregation_miss']]
summary={'history_classification':dict(counts),'source_misses':{'count':len(sm),'indexed_historical_papers_for_all':all(a['historical_papers_indexed']>0 for a in sm),'zero_query_token_overlap_in_all_indexed_titles':sum(a['best_token_overlap']==0 for a in sm),'no_bm25_title_match':sum(a['best_bm25_paper_rank'] is None for a in sm),'best_rank_1025_to_2048':sum(1024<min(a['best_bm25_paper_rank'] or 10**9,a['best_dense_paper_rank'])<=2048 for a in sm),'best_rank_2049_to_4096':sum(2048<min(a['best_bm25_paper_rank'] or 10**9,a['best_dense_paper_rank'])<=4096 for a in sm),'best_rank_beyond_4096':sum(min(a['best_bm25_paper_rank'] or 10**9,a['best_dense_paper_rank'])>4096 for a in sm),'median_best_dense_paper_rank':statistics.median(a['best_dense_paper_rank'] for a in sm)},'aggregation_misses':{'count':len(am),'median_rank':statistics.median(a['author_aggregation_rank'] for a,c in am),'within_rank_1000':sum(a['author_aggregation_rank']<=1000 for a,c in am),'within_rank_1600':sum(a['author_aggregation_rank']<=1600 for a,c in am),'lexical_only':sum(bool(a['lexical_author_rank']) and not a['dense_author_rank'] for a,c in am),'dense_only':sum(bool(a['dense_author_rank']) and not a['lexical_author_rank'] for a,c in am),'both_channels':sum(bool(a['dense_author_rank']) and bool(a['lexical_author_rank']) for a,c in am),'higher_title_token_overlap_than_boundary':sum(a['best_token_overlap']>c['best_token_overlap'] for a,c in am)}}
metrics={}
for depth, values in raw['depths'].items():
 vals=[r['elapsed_ms'] for r in values];metrics[depth]={'source_reached_instances':sum(r['reachable'] for r in values),'source_recall_known':sum(r['reachable'] for r in values)/534,'candidate_instances':sum(r['candidate'] for r in values),'candidate_recall_known':sum(r['candidate'] for r in values)/534,'candidate_recall_all':sum(r['candidate'] for r in values)/686,'queries_with_candidate':sum(r['hit'] for r in values),'query_hit':sum(r['hit'] for r in values)/129,'oracle_ndcg10':statistics.mean(r['oracle_ndcg'] for r in values),'candidate_context_ms_p50':float(np.percentile(vals,50)),'candidate_context_ms_p95':float(np.percentile(vals,95))}
trace={'scope':'Inspected 2024 development cohort only, future-authorship proxy labels, not human relevance or a final test. Author instances may repeat across queries.', 'labels_sha256':digest_file(root/'labels.jsonl'),'index_content_sha256':base['index_content_sha256'],'model_sha256':base['model_sha256'],'archive_scan':{'sha256':ar['archive_sha256'],'records_scanned':ar['records_scanned'],'elapsed_seconds':ar['elapsed_seconds']},'counts':summary,'rows':rows,'limitations':['Absence of exact source identity in a parseable dated title record is not proof of true absence elsewhere.','Same-name different-key records are ambiguous, not verified identity errors.','Token overlap is a weak descriptive signal, not a topical relevance label.','Dense rank uses strict greater-than; exact score ties may produce different deterministic positions.']}
(out/'phase5a-loss-attribution.json').write_text(json.dumps(trace,indent=2,ensure_ascii=False)+'\n')
(out/'phase5a-retrieval-depth.json').write_text(json.dumps({'scope':'Identical 129 inspected 2024 queries; historical graph through 2023; fixed 800 author cap; no reranking; sequential offline CPU; preencoded query; no grounding or HTTP.', 'labels_sha256':trace['labels_sha256'],'index_content_sha256':trace['index_content_sha256'],'depths':metrics,'elapsed_seconds':raw['elapsed_seconds'],'peak_rss_mib':raw['peak_rss_kb']/1024,'per_query':raw['depths']},indent=2)+'\n')
print(json.dumps({'summary':summary,'depths':metrics,'archive':trace['archive_scan']},indent=2))
