#!/usr/bin/env python3
"""Compare candidate budgets on one fixed, seeded validation-query cohort."""
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
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--queries', type=int, default=200)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--budgets', nargs='+', default=['256:200', '512:200', '512:400'],
                        help='Paper:author candidate limits')
    args = parser.parse_args()
    if args.out.exists() or args.queries < 1 or not args.db.is_file():
        parser.error('Use an existing database, a positive query count and a new output path')
    budgets = []
    for value in args.budgets:
        try:
            paper_limit, author_limit = map(int, value.split(':'))
            if paper_limit < 1 or author_limit < 1:
                raise ValueError()
        except ValueError:
            parser.error('Each budget must be positive integers PAPER:AUTHOR')
        budgets.append((paper_limit, author_limit))
    if len(set(budgets)) != len(budgets):
        parser.error('Budgets must be unique')
    database = connect(args.db)
    try:
        queries, labels_hash = load_partition(args.dataset, 'validation', database)
        selected = random.Random(args.seed).sample(queries, min(args.queries, len(queries)))
        encoder = LocalEncoder()
        model = json.loads(args.model.read_text())
        query_hash = hashlib.sha256('\n'.join(query.query_id for query in selected).encode()).hexdigest()
        comparisons = []
        for paper_limit, author_limit in budgets:
            engine = SearchIndex(database, args.index, encoder, paper_limit, author_limit)
            try:
                if model['training_content_sha256'] != engine.manifest['content_sha256']:
                    raise ValueError('Model and evaluation graph differ')
                started = monotonic()
                metrics, all_relevant, known_relevant, hits, candidates = [], 0, 0, 0, 0
                for query in selected:
                    retrieved = engine.retrieve(query.text)
                    ids = np.asarray(retrieved['author_ids'], dtype=np.int64)
                    relevant = set(query.relevant_author_ids)
                    all_relevant += len(relevant)
                    known_relevant += len(relevant & engine.authors.keys())
                    hits += len(relevant & set(ids.tolist()))
                    candidates += len(ids)
                    scores = score_model(retrieved['features'], model)
                    ranked = ids[np.lexsort((ids, -scores))].tolist()
                    metrics.append(ranking_metrics(ranked, relevant))
                elapsed = monotonic() - started
                comparisons.append({'paper_limit': paper_limit, 'author_limit': author_limit,
                    'queries': len(selected), 'all_relevant': all_relevant, 'known_relevant': known_relevant,
                    'candidate_hits': hits, 'candidate_recall_all': hits / all_relevant if all_relevant else None,
                    'candidate_recall_known': hits / known_relevant if known_relevant else None,
                    'mean_candidates': candidates / len(selected) if selected else 0,
                    'ndcg_at_10': float(np.mean([x['ndcg_at_10'] for x in metrics])) if metrics else None,
                    'mrr': float(np.mean([x['mrr'] for x in metrics])) if metrics else None,
                    'elapsed_seconds': round(elapsed, 3),
                    'mean_ms_per_query': round(elapsed * 1000 / len(selected), 3) if selected else None})
            finally:
                engine.close()
        report = {'scope': 'Seeded validation subset; existing model is not retrained. This is a development comparison, not a final test.',
                  'query_ids_sha256': query_hash, 'validation_labels_sha256': labels_hash,
                  'model_sha256': digest_file(args.model), 'package_source_sha256': package_digest(),
                  'seed': args.seed, 'comparisons': comparisons, 'command': sys.argv}
        write_json(args.out, report)
        print(json.dumps(report, indent=2))
    finally:
        database.close()


if __name__ == '__main__':
    main()
