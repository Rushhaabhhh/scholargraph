#!/usr/bin/env python3
"""Score blinded human review only when a method's entire top ten is judged."""
import argparse,csv,json,math,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import write_json
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reviews',type=Path,required=True);p.add_argument('--pool',type=Path,default=Path('data/research/experiments/phase3-judgment-pool.jsonl'));p.add_argument('--methods',type=Path,default=Path('data/research/results/phase3-pool-methods-private.json'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise ValueError('Use a new report path')
pool=[json.loads(x) for x in a.pool.read_text().splitlines()];valid={(x['query_id'],str(x['person_id'])) for x in pool};grades={};reviewers={}
with a.reviews.open(newline='') as f:
 for row in csv.DictReader(f):
  grade=row.get('grade_0_to_3','').strip();reviewer=row.get('reviewer','').strip();key=(row['query_id'],row['person_id'])
  if not grade:continue
  if key not in valid or grade not in ('0','1','2','3') or not reviewer:raise ValueError('Review must have valid pool ID, grade 0–3, and reviewer')
  if (key,reviewer) in reviewers:raise ValueError('Duplicate reviewer grade')
  reviewers[key,reviewer]=int(grade);grades.setdefault(key,[]).append(int(grade))
if not reviewers:raise ValueError('No actual human judgments provided')
methods=json.loads(a.methods.read_text())['methods'];outputs={}
for method in ('lexical','dense','hybrid','trained'):
 rows=[];unjudged_queries=0
 for item in methods:
  q=item['query_id'];ids=item['methods'][method];entries=[grades.get((q,str(i))) for i in ids]
  if any(x is None for x in entries):unjudged_queries+=1;continue
  # Median is explicit conflict aggregation; per-reviewer agreement is separate.
  vals=[statistics.median(x) for x in entries];ideal=sorted((statistics.median(v) for (query,_),v in grades.items() if query==q),reverse=True)[:10]
  dcg=sum((2**v-1)/math.log2(i+2) for i,v in enumerate(vals));idcg=sum((2**v-1)/math.log2(i+2) for i,v in enumerate(ideal));first=next((i+1 for i,v in enumerate(vals) if v>=2),0)
  rows.append({'ndcg_at_10_pooled_ideal':dcg/idcg if idcg else 0,'precision_at_10':sum(v>=2 for v in vals)/10,'mrr_at_10':1/first if first else 0})
 outputs[method]={'fully_judged_queries':len(rows),'excluded_queries_with_unjudged_results':unjudged_queries,'metrics':{k:statistics.fmean(r[k] for r in rows) for k in rows[0]} if rows else None}
agreements=[int(v[0]==v[1]) for v in grades.values() if len(v)==2]
report={'scope':'Human-supplied grades only; queries with unjudged top-ten results excluded per method, judged-pool ideal only. Query-selection bias and incomplete pool mean metrics are not exhaustive.','judged_pairs':len(grades),'pool_pairs':len(valid),'pool_coverage':len(grades)/len(valid),'two_reviewer_pairs':len(agreements),'two_reviewer_exact_agreement':statistics.fmean(agreements) if agreements else None,'metrics':outputs}
write_json(a.out,report);print(json.dumps(report,indent=2))
