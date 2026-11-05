#!/usr/bin/env python3
"""Prepare a year-balanced XML acceptance slice outside the training portfolio."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,title_key,write_json
from hiresense.data.dblp import iter_publications
from hiresense.data.history import _serialize
from hiresense.db import connect

out=Path('data/processed/recovery-transfer-v2')
if out.exists():raise ValueError('Use a fresh transfer directory')
source=connect('data/processed/recovery-v2/source.sqlite3')
raw=Path('data/raw/dblp.xml.gz');prefixes=('conf/icsoc/','conf/icws/')
portfolio=json.loads(Path('experiments/recovery-data-v2.json').read_text())['key_prefixes']
if any(p.startswith(tuple(portfolio)) for p in prefixes):raise ValueError('Transfer venues overlap selected training families')
counts=Counter();selected=[];skipped=0
try:
    for paper in iter_publications(raw):
        if paper.year not in range(2020,2025) or not paper.authors or not paper.key.startswith(prefixes) or counts[paper.year]>=25:
            continue
        if source.execute('SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1',(paper.key,title_key(paper.title))).fetchone():
            skipped+=1;continue
        selected.append(paper);counts[paper.year]+=1
        if len(selected)==125:break
    if len(selected)!=125:raise ValueError('Insufficient disjoint papers for year quotas')
    out.mkdir(parents=True)
    with (out/'source.xml').open('wb') as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
        for paper in selected:f.write(_serialize(paper))
        f.write(b'</dblp>\n')
    (out/'queries.txt').write_text('service composition and workflow optimization\nmicroservice reliability and cloud orchestration\nweb service discovery and semantic matching\n')
    write_json(out/'manifest.json',{'scope':'Different-domain disjoint XML functional acceptance only; no expert relevance accuracy claim.',
        'prefixes':list(prefixes),'year_counts':dict(counts),'papers':len(selected),
        'overlap_with_development_keys_or_titles':0,'overlapping_candidates_skipped':skipped,
        'data_sha256':digest_file(out/'source.xml'),'queries_sha256':digest_file(out/'queries.txt'),
        'raw_sha256':digest_file(raw),'training_portfolio_sha256':digest_file('experiments/recovery-data-v2.json'),
        'runner_sha256':digest_file(__file__)})
    print(json.dumps({'papers':len(selected),'year_counts':dict(counts),'directory':str(out)}))
finally:source.close()
