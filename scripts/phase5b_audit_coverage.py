import csv,json,sqlite3,collections,tempfile,sys,time
from pathlib import Path
sys.path.insert(0,'src')
from hiresense.api.runtime import Backend
pool=[json.loads(x) for x in Path('data/research/experiments/phase3-judgment-pool.jsonl').read_text().splitlines()];q=[json.loads(x) for x in Path('data/research/experiments/phase3-human-queries.jsonl').read_text().splitlines()]; method=json.load(open('data/research/results/phase3-pool-methods-private.json'))['methods'];counts=collections.Counter((x['query_id'],x['person_id']) for x in pool); pairs=set(counts); duplicate={str(k):v for k,v in counts.items() if v>1};issues=[];missing=[]; actual={}; stamp=time.monotonic()
with tempfile.TemporaryDirectory(prefix='phase5b-') as tmp:
 b=Backend.load('data/research/experiments/backend.json',session_db_override=Path(tmp)/'sessions.sqlite')
 try:
  for row in pool:
   if not row['evidence']:issues.append([row['query_id'],row['person_id'],'empty'])
   for paper in row['evidence']:
    rec=b.database.execute('select title,year,venue from papers where id=?',(paper['paper_id'],)).fetchone();link=b.database.execute('select 1 from paper_authors where paper_id=? and author_id=?',(paper['paper_id'],row['person_id'])).fetchone()
    if not rec or not link or tuple(rec)!=(paper['title'],paper['year'],paper['venue']) or not paper['year'] or paper['year']>2024:issues.append([row['query_id'],row['person_id'],paper['paper_id'],'invalid, undated, out-of-cutoff or mismatch'])
  for i,item in enumerate(q):
   response=b.search({'query':item['query']}); ids=[p['person_id'] for p in response['results']];actual[item['query_id']]=ids
   missing.extend([[item['query_id'],a] for a in ids if (item['query_id'],a) not in pairs])
   if (i+1)%10==0:print('production',i+1,flush=True)
  report={'queries':len(q),'pooled_rows':len(pool),'unique_pairs':len(pairs),'duplicates':duplicate,'evidence_issues':issues,'production_missing_pairs':missing,'production_ranked':actual,'production_result_count_by_query':{k:len(v) for k,v in actual.items()},'recorded_trained_missing':[[r['query_id'],a] for r in method for a in r['methods']['trained'] if (r['query_id'],a) not in pairs],'cutoff':b.engine.anchor_year,'elapsed_seconds':round(time.monotonic()-stamp,2),'index_content_sha256':b.engine.manifest['content_sha256']}
  Path('/tmp/phase5b-audit.json').write_text(json.dumps(report,indent=2));print('audit done',len(missing),len(issues),flush=True)
 finally:b.close()
