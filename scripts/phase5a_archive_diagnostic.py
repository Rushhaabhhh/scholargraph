import json,sqlite3,time,sys
from pathlib import Path
sys.path.insert(0,'src')
from hiresense.data.dblp import iter_publications
from hiresense.data.ingest import stable_id
from hiresense.data.artifacts import digest_file
from hiresense.evaluation.split import load_queries
root=Path('data/processed/lean-v1/validation'); queries=load_queries(root/'labels.jsonl'); baseline=json.load(open('resources/results/phase1-baseline-funnel-v1.json')); ids={a for row in baseline['rows'] for a in row['stage_ids']['no_history']}
src=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
keys={a:src.execute('select source_key from authors where id=?',(a,)).fetchone()[0] for a in ids}; key_to_id={v:k for k,v in keys.items()}; found={}; names={}
for a,key in keys.items():
 name=src.execute('select observed_name from paper_authors where author_id=? limit 1',(a,)).fetchone()
 if name:names.setdefault(name[0],[]).append(a)
name_mismatch={};count=0;start=time.time()
for p in iter_publications('data/raw/dblp.xml.gz'):
 count+=1
 if not p.year or p.year>2023:continue
 for name,pid in zip(p.authors,p.author_pids):
  k='dblp:pid:'+pid if pid else 'dblp:name:'+name
  if k in key_to_id:
   a=key_to_id[k]
   if a not in found:found[a]={'id':p.key,'year':p.year,'title':p.title}
  if name in names:
   for a in names[name]:
    if k!=keys[a] and a not in name_mismatch:name_mismatch[a]={'id':p.key,'year':p.year,'name':name,'other_key':k}
 if count%2000000==0:print(count,round(time.time()-start),flush=True)
result={'archive_sha256':digest_file('data/raw/dblp.xml.gz'),'records_scanned':count,'elapsed_seconds':round(time.time()-start,1),'exact':found,'same_name_different_key':name_mismatch,'scope':'exact PID or fallback-name join; same-name mismatch is an ambiguity not proof of identity'}
Path('/tmp/phase5a-archive.json').write_text(json.dumps(result));print('done',len(found),len(name_mismatch),flush=True)
