#!/usr/bin/env python3
"""Materialize training/validation features and audit a fixed pilot without training."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition, materialize
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('graph-db', 'index', 'dataset', 'cache', 'model', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists() or not args.graph_db.is_file():
        parser.error('Use an existing graph and new output report')
    graph = connect(args.graph_db)
    engine = None
    try:
        encoder = LocalEncoder()
        engine = SearchIndex(graph, args.index, encoder)
        model = json.loads(args.model.read_text())
        if model['encoder_sha256'] != encoder.signature:
            raise ValueError('Model and encoder differ')
        summaries, caches = {}, {}
        for role in ('train', 'validation'):
            queries, sha = load_partition(args.dataset, role, graph)
            cache = materialize(engine, queries, args.cache / f'features-{role}', sha)
            caches[role] = cache
            known = set(engine.authors)
            positives = known_positives = candidates_found = usable = 0
            for i, query in enumerate(queries):
                start, end = cache['offsets'][i:i + 2]
                ids = set(cache['author_ids'][start:end].tolist())
                relevant = set(query.relevant_author_ids)
                positives += len(relevant)
                known_positives += len(relevant & known)
                candidates_found += len(relevant & ids)
                usable += bool(relevant & ids) and bool(ids - relevant)
            summaries[role] = {'queries': len(queries), 'candidate_rows': len(cache['author_ids']),
                               'relevant_authors': positives, 'known_authors': known_positives,
                               'candidate_hits': candidates_found, 'queries_with_positive_and_contrast': usable,
                               'history_coverage': known_positives / positives if positives else None,
                               'candidate_recall_all': candidates_found / positives if positives else None,
                               'candidate_recall_known': candidates_found / known_positives if known_positives else None,
                               'labels_sha256': sha}
        evaluation = evaluate_rankings(engine, caches['validation'], {'baseline_trained_model': model})
        # The generic evaluator computes paired comparisons only for a model named 'learned';
        # the transferred baseline is explicitly labeled rather than presented as newly trained.
        report = {'scope': 'Fixed training/validation pilot; no training or reserved-test evaluation.',
                  'limitation': 'Baseline model was trained on another graph and validated on an earlier cohort; '
                                'this is a development comparison, not an external generalization claim.',
                  'summaries': summaries, 'validation_metrics': evaluation['metrics'],
                  'validation_cohorts': evaluation['cohorts'],
                  'cache_manifests': {role: digest_file(args.cache / f'features-{role}/manifest.json')
                                      for role in caches},
                  'model_sha256': digest_file(args.model), 'package_source_sha256': package_digest(),
                  'command': sys.argv}
        write_json(args.out, report)
        print(json.dumps(report, indent=2))
    finally:
        if engine is not None:
            engine.close()
        graph.close()


if __name__ == '__main__':
    main()
