#!/usr/bin/env python3
"""Evaluate a validation-frozen ranker once on the reserved 2025 cohort."""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import monotonic

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import materialize
from hiresense.evaluation.ranking import evaluate_rankings, name_counterfactual
from hiresense.evaluation.split import assert_no_leakage, dataset_digest, export_snapshot, load_queries
from hiresense.graph.build import build_context_graph, validate_graph
from hiresense.models import GroundTruthQuery
from hiresense.ranking.service import search
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex, build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, default=Path('resources/experiments/lean-freeze-v1.json'))
    parser.add_argument('--data', type=Path, default=Path('data/processed/lean-v1'))
    parser.add_argument('--out', type=Path, default=Path('resources/results/lean-final-v1.json'))
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('A final report already exists; never overwrite an evaluated test')
    frozen = json.loads(args.freeze.read_text())
    if frozen['package_source_sha256'] != package_digest():
        raise ValueError('Package changed after model freeze')
    paths = {key: Path(frozen[key]) for key in ('model', 'ablation_model', 'test_ids')}
    # Older frozen manifests used pre-reorganization paths. These fallbacks
    # remain subject to the original SHA-256 checks below.
    for key, fallback in (('model', 'models/hybrid_ranker.json'),
                          ('ablation_model', 'models/lean_without_recency.json'),
                          ('test_ids', 'resources/experiments/lean-test-ids.json')):
        if not paths[key].exists():
            paths[key] = Path(fallback)
    for key, checksum in (('model', 'model_sha256'), ('ablation_model', 'ablation_sha256'), ('test_ids', 'test_ids_sha256')):
        if digest_file(paths[key]) != frozen[checksum]:
            raise ValueError(f'Frozen {key} changed')
    if digest_file(frozen.get('validation_report', 'resources/results/lean-validation-v1.json')) != frozen['validation_report_sha256']:
        raise ValueError('Validation report changed after freeze')
    model = json.loads(paths['model'].read_text())
    ablation = json.loads(paths['ablation_model'].read_text())
    reserved = json.loads(paths['test_ids'].read_text())
    ids = reserved['source_paper_ids']
    if reserved['year'] != 2025 or len(ids) != len(set(ids)):
        raise ValueError('Invalid reserved test IDs')
    source = connect(args.data / 'source.sqlite3')
    test_dir = args.data / 'test'
    test_dir.mkdir(parents=True, exist_ok=True)
    graph = engine = None
    started = monotonic()
    try:
        if dataset_digest(source) != frozen['source_dataset_sha256']:
            raise ValueError('Selected source differs from the frozen training source')
        graph_path = test_dir / 'graph.sqlite3'
        if graph_path.exists() and not (test_dir / 'graph.json').exists():
            raise ValueError('Incomplete test graph exists; move or remove that generated directory before retrying')
        if not graph_path.exists():
            counts = export_snapshot(source, graph_path, 2024, frozen['source_dataset_sha256'])
            graph = connect(graph_path)
            graph_info = build_context_graph(graph)
            write_json(test_dir / 'graph.json', {'snapshot': counts, 'graph': graph_info})
            graph.close()
        graph = connect(graph_path)
        validate_graph(graph)
        if graph.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0] != frozen['source_dataset_sha256']:
            raise ValueError('Test graph source differs')
        queries = []
        for identifier in ids:
            paper = source.execute('SELECT id,title,year FROM papers WHERE id=?', (identifier,)).fetchone()
            authors = tuple(row[0] for row in source.execute('SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position', (identifier,)))
            if not paper or paper['year'] != 2025 or not authors:
                raise ValueError('Reserved test paper missing or has no authors')
            queries.append(GroundTruthQuery(identifier, paper['title'], identifier, paper['year'], authors))
        assert_no_leakage(graph, queries, [], 2024)
        labels = test_dir / 'labels.jsonl'
        if labels.exists():
            if load_queries(labels) != queries:
                raise ValueError('Existing test labels differ')
        else:
            labels.write_text(''.join(json.dumps(asdict(q), ensure_ascii=False, sort_keys=True) + '\n' for q in queries), encoding='utf-8')
        encoder = LocalEncoder()
        if not (test_dir / 'index').exists():
            if (args.data / 'validation/index/manifest.json').is_file():
                reference = connect(args.data / 'validation/graph.sqlite3')
                try:
                    info = build_index(graph, test_dir / 'index', encoder,
                                       reuse_index=args.data / 'validation/index', reuse_database=reference)
                finally:
                    reference.close()
            else:
                info = build_index(graph, test_dir / 'index', encoder)
            print(json.dumps({'test_index': info}), flush=True)
        engine = SearchIndex(graph, test_dir / 'index', encoder, **model['retrieval'])
        cache = materialize(engine, queries, test_dir / 'features', digest_file(labels))
        evaluation = evaluate_rankings(engine, cache, {'learned': model, 'without_recency': ablation}, bootstrap_samples=1000)
        timings = []
        for query in queries[:20]:
            before = monotonic()
            search(engine, query.text, model)
            timings.append((monotonic()-before)*1000)
        fairness = name_counterfactual(engine, model, queries[:8])
        report = {'scope': 'One frozen, in-domain 2025 future-authorship test; sampled labels are incomplete expert judgments. Model and retrieval selected on inspected validation only.',
                  'freeze_sha256': digest_file(args.freeze), 'test_ids_sha256': frozen['test_ids_sha256'],
                  'labels_sha256': digest_file(labels), 'graph_cutoff_year': 2024, 'graph_papers': len(engine.papers),
                  'model_sha256': frozen['model_sha256'], 'evaluation': evaluation, 'name_counterfactual': fairness,
                  'latency_ms': {'p50': float(np.percentile(timings,50)), 'p95': float(np.percentile(timings,95)),
                                 'samples': len(timings), 'scope': 'Sequential warm search with query encoding and ranker, not HTTP or throughput.'},
                  'ablation_scope': 'Explicit recency features removed with fixed candidate generation; other features may retain temporal information.',
                  'elapsed_seconds': round(monotonic()-started,3), 'command': sys.argv}
        if package_digest() != frozen['package_source_sha256']:
            raise ValueError('Package changed during evaluation')
        write_json(args.out, report)
        print(json.dumps({'metrics': evaluation['metrics'], 'coverage': evaluation['coverage'], 'report': str(args.out)}, indent=2))
    finally:
        if engine:
            engine.close()
        if graph:
            graph.close()
        source.close()


if __name__ == '__main__':
    main()
