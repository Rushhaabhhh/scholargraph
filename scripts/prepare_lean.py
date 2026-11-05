#!/usr/bin/env python3
"""Prepare bounded, chronological expert-search data from a verified DBLP source."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, title_key, write_json
from hiresense.db import connect, initialize
from hiresense.evaluation.split import assert_no_leakage, dataset_digest, export_snapshot, load_queries
from hiresense.graph.build import build_context_graph


def read_window(path):
    manifest = json.loads((path / 'manifest.json').read_text())
    labels = path / 'labels.jsonl'
    if digest_file(labels) != manifest['labels_sha256']:
        raise ValueError(f'Invalid cohort digest: {path}')
    return load_queries(labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--expected-test-ids', type=Path, help='Reject a repeat if the reserved IDs differ')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    output = Path(config['output'])
    if output.exists():
        raise ValueError('Output exists; choose a fresh directory')
    source_xml = Path(config['source_xml'])
    ingestion = json.loads(Path(config['source_ingestion_report']).read_text())
    source_sha = digest_file(source_xml)
    if source_sha != ingestion['source_sha256']:
        raise ValueError('Source XML differs from ingestion report')
    source = sqlite3.connect(f"{Path(config['source_db']).resolve().as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output.parent, prefix='.lean-'))
    started = monotonic()
    try:
        run = source.execute("SELECT source_sha256,records_loaded,status FROM ingestion_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not run or run['status'] != 'completed' or run['source_sha256'] != source_sha or run['records_loaded'] != source.execute('SELECT COUNT(*) FROM papers').fetchone()[0]:
            raise ValueError('Source DB ingestion provenance differs')
        source_manifest = json.loads((Path(config['validation_window']) / 'manifest.json').read_text())
        if dataset_digest(source) != source_manifest['source_dataset_sha256']:
            raise ValueError('Source DB content differs from the cohort source')
        qprefix = tuple(config['query_prefixes'])
        prefixes = qprefix + tuple(config['additional_history_prefixes'])
        if not prefixes or len(set(prefixes)) != len(prefixes) or any(not p.endswith('/') for p in prefixes):
            raise ValueError('Invalid or repeated venue-key prefixes')
        selected = [row['id'] for row in source.execute('SELECT id,year FROM papers WHERE year BETWEEN ? AND ? AND record_type IN (\'article\',\'inproceedings\')', (config['min_year'], config['max_year'])) if row['id'].startswith(prefixes)]
        selected_paper_ids = set(selected)
        target = connect(stage / 'source.sqlite3')
        try:
            initialize(target)
            target.execute('ATTACH DATABASE ? AS origin', (str(Path(config['source_db']).resolve()),))
            target.execute('CREATE TEMP TABLE selected(id TEXT PRIMARY KEY) WITHOUT ROWID')
            target.executemany('INSERT INTO selected VALUES(?)', ((p,) for p in selected))
            with target:
                target.execute('INSERT INTO papers SELECT p.* FROM origin.papers p JOIN selected s ON p.id=s.id')
                target.execute('INSERT INTO authors SELECT a.* FROM origin.authors a WHERE EXISTS (SELECT 1 FROM origin.paper_authors pa JOIN selected s ON s.id=pa.paper_id WHERE pa.author_id=a.id)')
                target.execute('INSERT INTO paper_authors SELECT pa.* FROM origin.paper_authors pa JOIN selected s ON pa.paper_id=s.id')
                target.execute('INSERT INTO venues SELECT v.* FROM origin.venues v WHERE EXISTS (SELECT 1 FROM origin.paper_venues pv JOIN selected s ON s.id=pv.paper_id WHERE pv.venue_id=v.id)')
                target.execute('INSERT INTO paper_venues SELECT pv.* FROM origin.paper_venues pv JOIN selected s ON pv.paper_id=s.id')
            if target.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Source selection has broken foreign keys')
            source_content = dataset_digest(target)
            print(f'Selected {len(selected):,} papers; preparing temporal graphs.', flush=True)
            prior = []
            for path in config['previous_evaluation_labels']:
                prior += load_queries(path)
            prior_ids = {q.source_paper_id for q in prior}
            prior_titles = {title_key(q.text) for q in prior}
            train = [q for p in config['train_windows'] for q in read_window(Path(p)) if q.source_paper_id.startswith(qprefix)]
            validation = [q for q in read_window(Path(config['validation_window'])) if q.source_paper_id.startswith(qprefix)]
            if not train or not validation:
                raise ValueError('Empty selected cohort')
            if any(not 2020 < q.year <= 2023 for q in train) or any(q.year != 2024 for q in validation):
                raise ValueError('Selected cohort is outside its temporal window')
            ids, titles = set(), set()
            for query in train + validation:
                key = title_key(query.text)
                if (query.source_paper_id in ids or key in titles or query.source_paper_id in prior_ids or key in prior_titles):
                    raise ValueError('Selected cohort overlaps another partition or prior evaluation')
                paper = source.execute('SELECT title_key,year FROM papers WHERE id=?', (query.source_paper_id,)).fetchone()
                authors = tuple(row[0] for row in source.execute('SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position', (query.source_paper_id,)))
                if not paper or paper['title_key'] != key or paper['year'] != query.year or authors != query.relevant_author_ids:
                    raise ValueError('Selected label differs from the source publication')
                if source.execute('SELECT COUNT(*) FROM papers WHERE title_key=?', (key,)).fetchone()[0] != 1:
                    raise ValueError('Selected label has a repeated source title')
                ids.add(query.source_paper_id)
                titles.add(key)
            all_ids = {q.source_paper_id for q in train + validation} | prior_ids
            all_titles = {title_key(q.text) for q in train + validation} | prior_titles
            # Select only paper IDs/titles, never future author labels. Exclude duplicate titles across the full source.
            choices = []
            for row in source.execute('SELECT id,title_key FROM papers WHERE year=2025'):
                if row['id'] not in selected_paper_ids or not row['id'].startswith(qprefix) or row['id'] in all_ids or row['title_key'] in all_titles:
                    continue
                if source.execute('SELECT COUNT(*) FROM papers WHERE title_key=?', (row['title_key'],)).fetchone()[0] != 1:
                    continue
                priority = hashlib.sha256(f"{config['seed']}:test:{row['id']}".encode()).hexdigest()
                choices.append((priority, row['id']))
            ids = [p for _, p in sorted(choices)[:config['test_sample_size']]]
            if not ids:
                raise ValueError('No eligible final test IDs')
            if args.expected_test_ids and ids != json.loads(args.expected_test_ids.read_text())['source_paper_ids']:
                raise ValueError('Reserved test IDs differ from the recorded selection')
            write_json(stage / 'reserved-test-ids.json', {'year': 2025, 'source_paper_ids': ids, 'eligible_count': len(choices), 'selection': 'SHA256 seeded order; no future author labels used'})
            for role, cutoff, queries in (('train', 2020, train), ('validation', 2023, validation)):
                directory = stage / role
                directory.mkdir()
                snapshot = export_snapshot(target, directory / 'graph.sqlite3', cutoff, source_content)
                graph = connect(directory / 'graph.sqlite3')
                try:
                    graph_report = build_context_graph(graph)
                    assert_no_leakage(graph, queries, [], cutoff)
                finally:
                    graph.close()
                original = [Path(p) / 'labels.jsonl' for p in (config['train_windows'] if role == 'train' else [config['validation_window']])]
                selected_ids = {q.source_paper_id for q in queries}
                with (directory / 'labels.jsonl').open('w', encoding='utf-8') as out:
                    for path in original:
                        for line in path.read_text(encoding='utf-8').splitlines():
                            if json.loads(line)['source_paper_id'] in selected_ids:
                                out.write(line + '\n')
                write_json(directory / 'manifest.json', {'role': role, 'cutoff': cutoff, 'queries': len(queries), 'labels_sha256': digest_file(directory / 'labels.jsonl'), 'source_dataset_sha256': source_content, 'snapshot': snapshot, 'graph': graph_report, 'parents': {str(p): digest_file(p) for p in original}})
                print(f'{role}: {snapshot["papers"]:,} papers; {len(queries)} queries.', flush=True)
            write_json(stage / 'manifest.json', {'config': config, 'config_sha256': digest_file(args.config), 'original_source_xml_sha256': source_sha, 'selected_source_dataset_sha256': source_content, 'papers': len(selected), 'train_queries': len(train), 'validation_queries': len(validation), 'reserved_test_ids': len(ids), 'query_families': dict(Counter('/'.join(q.source_paper_id.split('/')[:2]) for q in validation)), 'limits': 'Development selection uses inspected validation labels; historical venue selection was fixed independently of target-author IDs. Future authorship is an incomplete proxy for expertise. The test IDs have no materialized author labels.', 'elapsed_seconds': round(monotonic()-started, 3)})
            target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            target.close()
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage)
        raise
    finally:
        source.close()
    print(f'Prepared {output}', flush=True)


if __name__ == '__main__':
    main()
