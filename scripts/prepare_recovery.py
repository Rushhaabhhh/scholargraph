#!/usr/bin/env python3
"""Build rolling, source-bound graphs and fresh deterministic query cohorts."""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file, write_json, title_key
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.split import load_queries, dataset_digest, export_snapshot, assert_no_leakage
from hiresense.graph.build import build_context_graph
from hiresense.models import GroundTruthQuery
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import build_index


def select_queries(source, window, seed, excluded_ids, excluded_titles, duplicate_titles, key_prefixes=()):
    buckets = defaultdict(list)
    for key,title,year in source.execute('SELECT id,title,year FROM papers WHERE year BETWEEN ? AND ? ORDER BY id',
                                        (window['start'],window['end'])):
        if key_prefixes and not key.startswith(tuple(key_prefixes)):
            continue
        normalized = title_key(title)
        if key in excluded_ids or normalized in excluded_titles or normalized in duplicate_titles:
            continue
        authors = tuple(r[0] for r in source.execute('SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position',(key,)))
        if not authors:
            continue
        q = GroundTruthQuery(key,title,key,year,authors)
        family = '/'.join(key.split('/')[:2])
        priority = hashlib.sha256(f"{seed}:{window['role']}:{key}".encode()).digest()
        buckets[family].append((priority,q))
    for rows in buckets.values():
        rows.sort(key=lambda x:(x[0],x[1].query_id))
    selected=[]
    offset=0
    while len(selected)<window['queries']:
        found=False
        for family in sorted(buckets):
            if offset<len(buckets[family]):
                selected.append(buckets[family][offset][1]);found=True
                if len(selected)==window['queries']:
                    break
        if not found:
            break
        offset+=1
    if len(selected)!=window['queries']:
        raise ValueError(f"Only {len(selected)} eligible {window['role']} queries")
    return selected,{k:len(v) for k,v in buckets.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    config=json.loads(args.config.read_text());work=Path(config['work'])
    output=work/'preparation.json'
    if output.exists():
        raise ValueError('Preparation report already exists; use a fresh work/config')
    source=connect(work/'source.sqlite3');initialize(source)
    reports={}
    try:
        if source.execute('SELECT COUNT(*) FROM papers').fetchone()[0]==0:
            write_json(work/'ingestion.json',ingest(source,config['source']))
        reports['repeated_ingestion']=ingest(source,config['source'])
        origin=dataset_digest(source)
        excluded_ids,excluded_titles=set(),set();excluded_hashes={}
        for file in config['exclude_evaluation_labels']:
            for q in load_queries(file):
                excluded_ids.add(q.source_paper_id);excluded_titles.add(title_key(q.text))
            excluded_hashes[file]=digest_file(file)
        duplicates={r[0] for r in source.execute('SELECT title_key FROM papers GROUP BY title_key HAVING COUNT(*)>1')}
        # Seal labels before scoring and before any retrieval/model choices.
        for window in config['windows']:
            directory=work/window['role'];directory.mkdir(parents=True,exist_ok=True)
            manifest=directory/'manifest.json'
            if manifest.exists():
                saved=json.loads(manifest.read_text())
                if saved['source_dataset_sha256'] != origin or saved['config_sha256'] != digest_file(args.config) or saved['labels_sha256'] != digest_file(directory/'labels.jsonl'):
                    raise ValueError('Prepared rolling labels differ from their manifest')
                reports[window['role']]=saved
                for q in load_queries(directory/'labels.jsonl'):
                    excluded_ids.add(q.source_paper_id);excluded_titles.add(title_key(q.text))
                continue
            queries,pools=select_queries(source,window,config['seed'],excluded_ids,excluded_titles,duplicates)
            labels=directory/'labels.jsonl'
            if labels.exists():
                raise ValueError(f'Incomplete output {directory}; inspect before resuming')
            labels.write_text(''.join(json.dumps(asdict(q),ensure_ascii=False,sort_keys=True)+'\n' for q in queries))
            write_json(manifest,{'window':window,'source_dataset_sha256':origin,
                'config_sha256':digest_file(args.config),'labels_sha256':digest_file(labels),
                'previous_evaluation_files_sha256':excluded_hashes,'eligible_by_family':pools,
                'sampling':config['sampling'],'limits':config['limits'],'seed':config['seed']})
            reports[window['role']]=json.loads(manifest.read_text())
            for q in queries:
                excluded_ids.add(q.source_paper_id);excluded_titles.add(title_key(q.text))
        encoder=LocalEncoder()
        previous=None
        for window in config['windows']:
            directory=work/window['role'];graph_file=directory/'graph.sqlite3'
            if not graph_file.exists():
                write_json(directory/'snapshot.json',export_snapshot(source,graph_file,window['cutoff'],origin))
            graph=connect(graph_file)
            try:
                queries=load_queries(directory/'labels.jsonl')
                if graph.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0] != origin:
                    raise ValueError('Rolling graph source differs from labels')
                assert_no_leakage(graph,[],queries,window['cutoff'])
                if not (directory/'graph.json').exists():
                    write_json(directory/'graph.json',build_context_graph(graph))
                if not (directory/'index').exists():
                    kwargs={}
                    previous_db=None
                    if previous is not None:
                        previous_db=connect(previous/'graph.sqlite3')
                        kwargs={'reuse_index':previous/'index','reuse_database':previous_db}
                    elif Path('data/indexes/recent-history/manifest.json').exists():
                        previous_db=connect('data/processed/recent-history/graph.sqlite3')
                        kwargs={'reuse_index':Path('data/indexes/recent-history'),'reuse_database':previous_db}
                    try:
                        write_json(directory/'index.json',build_index(graph,directory/'index',encoder,**kwargs))
                    finally:
                        if previous_db is not None:previous_db.close()
                print(f"Prepared {window['role']}: graph through {window['cutoff']}; {len(queries)} queries",flush=True)
                previous=directory
            finally:graph.close()
        write_json(output,{'config':config,'config_sha256':digest_file(args.config),
            'source_sha256':digest_file(config['source']),'source_dataset_sha256':origin,
            'windows':reports,'scope':'Prepared labels and rolling graphs only; no validation or test scoring.'})
    finally:source.close()

if __name__=='__main__':main()
