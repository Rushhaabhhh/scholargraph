#!/usr/bin/env python3
"""Reserve disjoint future-paper IDs without reading author labels for final evaluation."""
import argparse
import hashlib
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,title_key,write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=271828)
p.add_argument('--validation-count',type=int,default=200);p.add_argument('--final-count',type=int,default=300)
a=p.parse_args()
if a.out.exists():raise ValueError('Use a new output path')
if min(a.validation_count,a.final_count)<1:raise ValueError('Counts must be positive')
source=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
graphs={2024:sqlite3.connect('file:data/processed/lean-v1/validation/graph.sqlite3?mode=ro',uri=True),2025:sqlite3.connect('file:data/processed/recent-history/graph.sqlite3?mode=ro',uri=True)}
try:
 root=Path('data/processed');paths=sorted(set(root.rglob('*ground_truth.jsonl'))|set(root.rglob('labels.jsonl')))
 excluded,excluded_titles=set(),set();manifests=[]
 for file in paths:
  manifests.append({'path':str(file),'sha256':digest_file(file)})
  for line in file.read_text(encoding='utf-8').splitlines():
   if not line.strip():continue
   row=json.loads(line);excluded.add(row.get('source_paper_id',''))
   if row.get('text'):excluded_titles.add(title_key(row['text']))
 previous=Path('resources/results/ranker-trial-2025-v1.json')
 prior=json.loads(previous.read_text())['query_ids'];excluded.update(prior)
 for identifier in prior:
  row=source.execute('select title from papers where id=?',(identifier,)).fetchone()
  if row:excluded_titles.add(title_key(row[0]))
 test_ids=Path('resources/experiments/lean-test-ids.json');excluded.update(json.loads(test_ids.read_text())['source_paper_ids'])
 rng=random.Random(a.seed);reserved={};seen_titles=set();diagnostics={}
 for year,count in ((2024,a.validation_count),(2025,a.final_count)):
  graph=graphs[year];cutoff=year-1
  if graph.execute('select count(*) from papers where year is null or year>?',(cutoff,)).fetchone()[0]:raise ValueError('Graph is not strictly historical')
  if graph.execute('select count(*) from context_edges where edge_year is null or edge_year>?',(cutoff,)).fetchone()[0]:raise ValueError('Future or undated graph edge')
  rows=list(source.execute('select id,title,title_key from papers where year=? order by id',(year,)));rng.shuffle(rows);ids=[];skipped=0
  for identifier,title,key in rows:
   key=title_key(title)
   if not key or identifier in excluded or key in excluded_titles or key in seen_titles:skipped+=1;continue
   if graph.execute('select 1 from papers where id=? or title_key=? limit 1',(identifier,key)).fetchone():skipped+=1;continue
   # Author identity labels are deliberately not read for the final cohort.
   ids.append(identifier);seen_titles.add(key)
   if len(ids)==count:break
  if len(ids)<count:raise ValueError('Not enough eligible records')
  reserved['validation' if year==2024 else 'final']=ids
  diagnostics[str(year)]={'graph_cutoff':cutoff,'candidate_year_papers':len(rows),'examined':len(ids)+skipped,'skipped':skipped,'reserved':len(ids)}
 result={'scope':'New seeded ID reservation; final author labels were not read. Exact historical graph ID/title and available local prior-label exclusions applied; earlier exposure from archived or unrecorded experiments cannot be ruled out.',
         'command':sys.argv,'seed':a.seed,'source_db_sha256':digest_file('data/processed/lean-v1/source.sqlite3'),
         'excluded_local_label_files':manifests,'previous_300_query_report_sha256':digest_file(previous),'previous_test_ids_sha256':digest_file(test_ids),
         'diagnostics':diagnostics,'reserved_source_paper_ids':reserved,
         'limitations':['Exclusions cover available local label files and named prior reports, not all historical outputs or external exposures.',
                        'Exact normalized titles and IDs do not detect semantic duplicates.',
                        'Final authors and model outcomes remain unopened; reservation alone does not freeze a model or evaluation protocol.']}
 write_json(a.out,result);print(json.dumps({'diagnostics':diagnostics,'local_label_files':len(paths),'reservation_sha256':digest_file(a.out)},indent=2))
finally:
 source.close()
 for c in graphs.values():c.close()
