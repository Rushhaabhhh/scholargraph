#!/usr/bin/env python3
"""Check blinded review-pool publication provenance against graph records."""
import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,write_json
pool=Path('resources/experiments/phase3-judgment-pool.jsonl');out=Path('resources/results/phase3-evidence-identity-audit.json')
if out.exists():raise ValueError('Use a fresh output')
db=sqlite3.connect('file:data/processed/recent-history/graph.sqlite3?mode=ro',uri=True);total=0;failures=[];persons=set()
for line in pool.read_text().splitlines():
 row=json.loads(line);persons.add(row['person_id'])
 for p in row['evidence']:
  total+=1
  source=db.execute('select p.title,p.year,p.venue,p.source from papers p join paper_authors a on a.paper_id=p.id where p.id=? and a.author_id=?',(p['paper_id'],row['person_id'])).fetchone()
  if source is None or tuple(source)!=(p['title'],p['year'],p['venue'],p['source']) or (p['year'] is not None and p['year']>2024):failures.append({'person_id':row['person_id'],'paper_id':p['paper_id']})
keys=dict(db.execute('select case when source_key like ? then ? else ? end,count(*) from authors group by 1',('dblp:name:%','name_fallback','other')).fetchall());db.close()
report={'scope':'All blinded review-pool paper records and author links compared to the configured graph; graph consistency is not identity or topical correctness.','pool_sha256':digest_file(pool),'paper_author_entries':total,'unique_people':len(persons),'mismatches':failures,'author_key_counts':keys,'prior_noise_resolution_report':'resources/results/recovery-identity-v2.json','limitations':['Publication title and authorship consistency do not establish topical fit or human identity.','Name-based source keys and DBLP numeric suffixes are not a complete alias audit.','No human relevance grades are available.','Synthetic identity resolution metrics do not measure production graph merge rate.']}
write_json(out,report);print(json.dumps(report,indent=2))
