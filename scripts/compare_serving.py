#!/usr/bin/env python3
"""Compare the existing served model with the frozen candidate on validation only."""
import argparse
import json
import sys
from pathlib import Path
from time import monotonic

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.factory import search_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window', type=Path, default=Path('data/processed/lean-v1/validation'))
    parser.add_argument('--freeze', type=Path, default=Path('resources/experiments/lean-freeze-v1.json'))
    parser.add_argument('--old-model', type=Path, default=Path('models/previous_hybrid_ranker.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out
    if out.exists():
        raise ValueError('Use a fresh validation comparison report')
    directory = args.window
    manifest = json.loads((directory / 'manifest.json').read_text())
    labels = directory / 'labels.jsonl'
    if digest_file(labels) != manifest['labels_sha256']:
        raise ValueError('Validation labels changed')
    freeze = json.loads(args.freeze.read_text())
    if package_digest() != freeze['package_source_sha256']:
        raise ValueError('Package changed since freeze')
    validation_path = Path(freeze.get('validation_report', 'resources/results/lean-validation-v1.json'))
    if digest_file(validation_path) != freeze['validation_report_sha256']:
        raise ValueError('Validation report differs from freeze')
    validation = json.loads(validation_path.read_text())
    old_path = args.old_model
    old = json.loads(old_path.read_text())
    db = connect(directory / 'graph.sqlite3')
    engine = None
    try:
        queries = load_queries(labels)
        assert_no_leakage(db, queries, [], 2023)
        encoder = LocalEncoder()
        engine = search_index(db, directory / 'index', encoder, old, profiles=directory / 'author_profiles')
        scores, elapsed = [], []
        print(f'Comparing current served model on {len(queries)} validation queries.', flush=True)
        for query in queries:
            begin = monotonic()
            found = engine.retrieve(query.text)
            values = score_model(found['features'], old)
            ranked = [found['author_ids'][i] for i in sorted(range(len(values)), key=lambda i: (-float(values[i]), found['author_ids'][i]))]
            elapsed.append((monotonic()-begin)*1000)
            scores.append(ranking_metrics(ranked, set(query.relevant_author_ids)))
        comparison = validation['selected_comparison']['metrics']
        report = {'scope': 'Inspected 2024 validation labels on identical dated graph; current full production model including cross-encoder versus frozen paper-ranker candidate. Not final test.',
                  'labels_sha256': digest_file(labels), 'old_model_sha256': digest_file(old_path), 'new_model_sha256': freeze['model_sha256'],
                  'current_served': {k: float(np.mean([v[k] for v in scores])) for k in ('ndcg_at_10', 'mrr')},
                  'new_ranker': comparison['learned'], 'new_untrained_hybrid': comparison['hybrid'],
                  'current_warm_retrieval_and_ranking_ms': {'p50': float(np.percentile(elapsed, 50)), 'p95': float(np.percentile(elapsed, 95))},
                  'queries': len(queries)}
        write_json(out, report)
        print(json.dumps(report, indent=2))
    finally:
        if engine: engine.close()
        db.close()


if __name__ == '__main__':
    main()
