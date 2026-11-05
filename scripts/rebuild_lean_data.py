#!/usr/bin/env python3
"""Rebuild the frozen development graphs directly from the same DBLP archive."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, title_key, write_json
from hiresense.data.dblp import iter_publications
from hiresense.data.history import _serialize
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.split import assert_no_leakage, dataset_digest, export_snapshot, load_queries
from hiresense.graph.build import build_context_graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh output directory')
    cohorts = json.loads(Path('resources/experiments/lean-cohorts.json').read_text())
    if digest_file(args.archive) != cohorts['source_archive_sha256']:
        raise ValueError('DBLP archive differs from the snapshot used for the reported results')
    config = json.loads(Path('resources/experiments/lean-data.json').read_text())
    prefixes = tuple(config['query_prefixes'] + config['additional_history_prefixes'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=args.out.parent, prefix='.rebuild-'))
    started = monotonic()
    db = None
    try:
        xml = stage / 'selected.xml'
        count = scanned = 0
        with xml.open('wb') as out:
            out.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
            for paper in iter_publications(args.archive):
                scanned += 1
                if (paper.year is not None and config['min_year'] <= paper.year <= config['max_year']
                        and paper.record_type in ('article', 'inproceedings') and paper.key.startswith(prefixes)):
                    out.write(_serialize(paper))
                    count += 1
                if scanned % 1000000 == 0:
                    print(f'Scanned {scanned:,} records; selected {count:,}.', flush=True)
            out.write(b'</dblp>\n')
        db = connect(stage / 'source.sqlite3')
        initialize(db)
        ingest(db, xml)
        if dataset_digest(db) != cohorts['source_dataset_sha256']:
            raise ValueError('Selected source content differs from the frozen experiment')
        for role in ('train', 'validation'):
            spec = cohorts['windows'][role]
            directory = stage / role
            directory.mkdir()
            labels = directory / 'labels.jsonl'
            labels.write_text('\n'.join(spec['labels']) + '\n', encoding='utf-8')
            if digest_file(labels) != spec['labels_sha256']:
                raise ValueError('Locked cohort labels changed')
            queries = load_queries(labels)
            for q in queries:
                row = db.execute('SELECT title_key,year FROM papers WHERE id=?', (q.source_paper_id,)).fetchone()
                authors = tuple(r[0] for r in db.execute('SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position', (q.source_paper_id,)))
                if not row or row['title_key'] != title_key(q.text) or row['year'] != q.year or authors != q.relevant_author_ids:
                    raise ValueError('Locked label differs from rebuilt source')
            counts = export_snapshot(db, directory / 'graph.sqlite3', spec['cutoff'], cohorts['source_dataset_sha256'])
            graph = connect(directory / 'graph.sqlite3')
            try:
                report = build_context_graph(graph)
                assert_no_leakage(graph, queries, [], spec['cutoff'])
            finally:
                graph.close()
            write_json(directory / 'manifest.json', {'role': role, 'cutoff': spec['cutoff'], 'queries': len(queries),
                       'labels_sha256': digest_file(labels), 'source_dataset_sha256': cohorts['source_dataset_sha256'],
                       'snapshot': counts, 'graph': report})
            print(f'{role}: {counts["papers"]:,} historical papers; {len(queries)} queries.', flush=True)
        shutil.copyfile('resources/experiments/lean-test-ids.json', stage / 'reserved-test-ids.json')
        xml.unlink()
        db.close()
        db = None
        write_json(stage / 'manifest.json', {'source_dataset_sha256': cohorts['source_dataset_sha256'],
                   'archive_sha256': cohorts['source_archive_sha256'], 'papers': count, 'records_scanned': scanned,
                   'elapsed_seconds': round(monotonic()-started, 3), 'scope': 'Locked development cohorts; reserved 2025 IDs copied without opening their author labels.'})
        stage.rename(args.out)
    except BaseException:
        if db:
            db.close()
        shutil.rmtree(stage)
        raise
    print(f'Rebuilt {args.out}', flush=True)


if __name__ == '__main__':
    main()
