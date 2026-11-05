#!/usr/bin/env python3
"""Distinguish missing-slice history from missing exact-ID DBLP history, without enrichment."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from time import monotonic

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,write_json
from hiresense.data.dblp import iter_publications
from hiresense.data.ingest import stable_id
from hiresense.db import connect
from hiresense.evaluation.split import load_queries

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--window',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise ValueError('Use a fresh audit report')
manifest=json.loads((a.window/'manifest.json').read_text());labels=a.window/'labels.jsonl'
if digest_file(labels)!=manifest['labels_sha256']:raise ValueError('Window labels changed')
cutoff=manifest['window']['cutoff'];db=connect(a.window/'graph.sqlite3')
missing=Counter();total=known=0
for q in load_queries(labels):
    for author in q.relevant_author_ids:
        total+=1
        if db.execute('SELECT 1 FROM authors WHERE id=?',(author,)).fetchone():known+=1
        else:missing[author]+=1
db.close();targets=set(missing);earliest={};began=monotonic();scanned=0
for publication in iter_publications('data/raw/dblp.xml.gz'):
    scanned+=1
    if publication.year is None or publication.year>cutoff or not publication.authors:continue
    for i,name in enumerate(publication.authors):
        pid=publication.author_pids[i] if publication.author_pids else None
        author=stable_id(f'dblp:pid:{pid}' if pid else f'dblp:name:{name}')
        if author in targets and (author not in earliest or publication.year<earliest[author]['year']):
            earliest[author]={'year':publication.year,'paper_key':publication.key,'title':publication.title}
    if scanned%1000000==0:print(f'Coverage audit {scanned:,} records; {len(earliest)}/{len(targets)} missing identities have earlier raw history',flush=True)
sampling_loss=sum(missing[a] for a in earliest)
write_json(a.out,{'scope':'Diagnostic only: no records/identities added to graph and no model setting selected.',
    'window':str(a.window),'cutoff':cutoff,'labels_sha256':digest_file(labels),'raw_sha256':digest_file('data/raw/dblp.xml.gz'),
    'relevant_author_instances':total,'known_in_slice':known,'missing_in_slice':sum(missing.values()),
    'missing_instances_with_pre_cutoff_raw_history':sampling_loss,
    'missing_instances_without_pre_cutoff_exact_id_raw_history':sum(missing.values())-sampling_loss,
    'missing_unique_authors':len(missing),'missing_unique_with_raw_history':len(earliest),
    'examples':[{'person_id':author,'instances':missing[author],**item} for author,item in sorted(earliest.items())[:10]],
    'records_scanned':scanned,'elapsed_seconds':monotonic()-began,'runner_sha256':digest_file(__file__),
    'limitation':'Exact DBLP identity keys, not proof of a person having no prior research elsewhere. PID/name inconsistency or renamed labels can affect joins. This audit uses validation labels for diagnosis only and never author-targets graph enrichment.'})
print(str(a.out))
