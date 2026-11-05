#!/usr/bin/env python3
"""Seal portfolio-aligned queries before training; preserve initial unscored cohorts."""
import argparse
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,title_key,write_json
from hiresense.db import connect
from hiresense.evaluation.split import load_queries,dataset_digest,assert_no_leakage
from prepare_recovery import select_queries

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
p.add_argument('--allow-incomplete-test-graph',action='store_true',help='Seal labels from source while only the final graph finishes; train/validation indexes must exist')
a=p.parse_args()
c=json.loads(a.config.read_text());work=Path(c['work']);out=work/'cohort-preparation.json'
if out.exists():raise ValueError('Portfolio cohort already sealed')
if not (work/'preparation.json').exists() and not a.allow_incomplete_test_graph:
    raise ValueError('Complete graph/index preparation first')
for role in ('train-early','train-later','validation'):
    if not (work/role/'index/manifest.json').exists():raise ValueError('Training and validation indexes must be complete')
portfolio=json.loads(Path(c['portfolio']).read_text());source=connect(work/'source.sqlite3')
try:
    origin=dataset_digest(source);ids=set();titles=set();excluded={}
    for file in c['exclude_evaluation_labels']:
        for q in load_queries(file):ids.add(q.source_paper_id);titles.add(title_key(q.text))
        excluded[file]=digest_file(file)
    duplicates={r[0] for r in source.execute('SELECT title_key FROM papers GROUP BY title_key HAVING COUNT(*)>1')}
    reports={}
    for window in c['windows']:
        role=window['role'];directory=work/role
        backup=directory/'initial-unscored-cohort';backup.mkdir(exist_ok=True)
        for file in ('labels.jsonl','manifest.json'):
            if not (backup/file).exists():
                shutil.copy2(directory/file,backup/file)
        original=json.loads((backup/'manifest.json').read_text())
        if digest_file(backup/'labels.jsonl') != original['labels_sha256']:
            raise ValueError('Initial cohort backup differs from its manifest')
        queries,pools=select_queries(source,window,c['seed'],ids,titles,duplicates,portfolio['key_prefixes'])
        # Source-level key/title check is stronger than checking a subset snapshot.
        for q in queries:
            if q.year<=window['cutoff'] or source.execute('SELECT 1 FROM papers WHERE year<=? AND (id=? OR title_key=?) LIMIT 1',
                    (window['cutoff'],q.source_paper_id,title_key(q.text))).fetchone():
                raise ValueError('Portfolio labels overlap allowed history')
        if (directory/'index/manifest.json').exists():
            graph=connect(directory/'graph.sqlite3')
            try:assert_no_leakage(graph,[],queries,window['cutoff'])
            finally:graph.close()
        labels=directory/'labels.jsonl';labels.write_text(''.join(json.dumps(asdict(q),ensure_ascii=False,sort_keys=True)+'\n' for q in queries))
        manifest={'window':window,'source_dataset_sha256':origin,'config_sha256':digest_file(a.config),
            'labels_sha256':digest_file(labels),'portfolio_sha256':digest_file(c['portfolio']),
            'previous_evaluation_files_sha256':excluded,'eligible_by_family':pools,
            'sampling':c['sampling'],'limits':c['limits'],'seed':c['seed'],
            'rationale':c['rationale'],'initial_unscored_manifest_sha256':digest_file(backup/'manifest.json')}
        write_json(directory/'manifest.json',manifest);reports[role]=manifest
        for q in queries:ids.add(q.source_paper_id);titles.add(title_key(q.text))
    write_json(out,{'config':c,'config_sha256':digest_file(a.config),'portfolio_sha256':digest_file(c['portfolio']),
        'source_dataset_sha256':origin,
        'parent_preparation_sha256':digest_file(work/'preparation.json') if (work/'preparation.json').exists() else None,
        'parent_protocol_sha256':digest_file(c['parent_protocol']),
        'test_graph_preparation_in_progress':not (work/'preparation.json').exists(),
        'windows':reports,'scope':'Cohort correction before training or scoring; initial cohorts retained unscored; broad v1 regression unchanged.',
        'runner_sha256':digest_file(__file__)})
finally:source.close()
print(str(out))
