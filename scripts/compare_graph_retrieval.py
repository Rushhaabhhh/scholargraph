#!/usr/bin/env python3
"""Compare two graph sizes using identical validation queries and a fixed model."""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from time import monotonic

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, title_key, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-graph', 'expanded-graph', 'baseline-index', 'expanded-index', 'dataset', 'model', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--queries', type=int, default=200)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if args.out.exists() or args.queries < 1 or not args.baseline_graph.is_file() or not args.expanded_graph.is_file():
        parser.error('Use existing graph files, positive query count and a new output path')
    baseline, expanded = connect(args.baseline_graph), connect(args.expanded_graph)
    try:
        cutoffs = [db.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone() for db in (baseline, expanded)]
        if not all(cutoffs) or cutoffs[0][0] != cutoffs[1][0]:
            raise ValueError('Graph cutoffs differ')
        for db in (baseline, expanded):
            assert_no_leakage(db, [], [], int(cutoffs[0][0]))
        queries, labels_hash = load_partition(args.dataset, 'validation', baseline)
        safe = [q for q in queries if not any(db.execute('SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1',
                 (q.source_paper_id, title_key(q.text))).fetchone() for db in (baseline, expanded))]
        selected = random.Random(args.seed).sample(safe, min(args.queries, len(safe)))
        model = json.loads(args.model.read_text())
        encoder = LocalEncoder()
        results = []
        for name, database, index in (('baseline', baseline, args.baseline_index), ('expanded', expanded, args.expanded_index)):
            engine = SearchIndex(database, index, encoder)
            try:
                if name == 'baseline' and model['training_content_sha256'] != engine.manifest['content_sha256']:
                    raise ValueError('Baseline graph differs from model training graph')
                started = monotonic()
                all_relevant = known_relevant = hits = 0
                metrics = []
                for query in selected:
                    retrieved = engine.retrieve(query.text)
                    ids = np.asarray(retrieved['author_ids'], dtype=np.int64)
                    relevant = set(query.relevant_author_ids)
                    all_relevant += len(relevant)
                    known_relevant += len(relevant & engine.authors.keys())
                    hits += len(relevant & set(ids.tolist()))
                    scores = score_model(retrieved['features'], model)
                    metrics.append(ranking_metrics(ids[np.lexsort((ids, -scores))].tolist(), relevant))
                elapsed = monotonic() - started
                results.append({'graph': name, 'papers': len(engine.papers), 'authors': len(engine.authors),
                    'all_relevant': all_relevant, 'known_relevant': known_relevant, 'candidate_hits': hits,
                    'history_coverage': known_relevant / all_relevant if all_relevant else None,
                    'candidate_recall_all': hits / all_relevant if all_relevant else None,
                    'candidate_recall_known': hits / known_relevant if known_relevant else None,
                    'ndcg_at_10': float(np.mean([x['ndcg_at_10'] for x in metrics])) if metrics else None,
                    'mrr': float(np.mean([x['mrr'] for x in metrics])) if metrics else None,
                    'mean_ms_per_query': round(elapsed * 1000 / len(selected), 3) if selected else None})
            finally:
                engine.close()
        report = {'scope': 'Same sampled validation cohort, fixed baseline-trained model and 256:200 retrieval budgets; no retraining or final-test selection.',
                  'limitation': 'Expanded graph is source-order selected; training graph and expanded serving graph differ.',
                  'queries': len(selected), 'excluded_for_graph_title_or_key_overlap': len(queries) - len(safe),
                  'query_ids_sha256': hashlib.sha256('\n'.join(q.query_id for q in selected).encode()).hexdigest(),
                  'validation_labels_sha256': labels_hash, 'model_sha256': digest_file(args.model), 'seed': args.seed,
                  'package_source_sha256': package_digest(), 'comparison': results, 'command': sys.argv}
        write_json(args.out, report)
        print(json.dumps(report, indent=2))
    finally:
        baseline.close()
        expanded.close()


if __name__ == '__main__':
    main()
