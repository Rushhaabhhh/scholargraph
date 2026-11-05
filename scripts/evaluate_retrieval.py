#!/usr/bin/env python3
"""Measure bounded retrieval on a prepared validation window, without fitting a model."""
import argparse
import json
import statistics
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.hybrid import HybridIndex
from hiresense.retrieval.index import SearchIndex, build_index


def summarize(rows, known):
    total = retrieved = covered = successes = 0
    metrics, oracle, graph_oracle = [], [], []
    for query, ranking in rows:
        relevant = set(query.relevant_author_ids)
        historical = relevant & known
        hits = relevant & set(ranking)
        total += len(relevant)
        covered += len(historical)
        retrieved += len(hits)
        successes += bool(hits)
        metrics.append(ranking_metrics(ranking, relevant))
        oracle.append(ranking_metrics(sorted(hits), relevant))
        graph_oracle.append(ranking_metrics(sorted(historical), relevant))
    mean = lambda values, key: statistics.fmean(x[key] for x in values)
    return {'queries': len(rows), 'relevant_author_instances': total, 'known_instances': covered,
            'retrieved_relevant_instances': retrieved, 'history_coverage': covered / total,
            'candidate_recall_all': retrieved / total, 'candidate_recall_known': retrieved / covered if covered else None,
            'queries_with_relevant_candidate': successes / len(rows),
            'ndcg_at_10': mean(metrics, 'ndcg_at_10'), 'mrr': mean(metrics, 'mrr'),
            'candidate_oracle_ndcg_at_10': mean(oracle, 'ndcg_at_10'),
            'graph_oracle_ndcg_at_10': mean(graph_oracle, 'ndcg_at_10')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window', type=Path, required=True)
    parser.add_argument('--reuse-graph', type=Path, required=True)
    parser.add_argument('--reuse-index', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', choices=('current_hybrid_400', 'paper_hybrid_400', 'paper_hybrid_800', 'paper_hybrid_1600'))
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a fresh output path')
    manifest = json.loads((args.window / 'manifest.json').read_text())
    labels = args.window / 'labels.jsonl'
    if manifest['role'] != 'validation' or digest_file(labels) != manifest['labels_sha256']:
        raise ValueError('Validation window or label checksum differs')
    queries = load_queries(labels)
    db = connect(args.window / 'graph.sqlite3')
    ref = None
    engine = None
    try:
        if db.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0] != manifest['source_dataset_sha256']:
            raise ValueError('Graph provenance differs from labels')
        assert_no_leakage(db, queries, [], manifest['cutoff'])
        known = {r[0] for r in db.execute('SELECT id FROM authors')}
        encoder = LocalEncoder()
        index = args.window / 'index'
        if not index.exists():
            ref = connect(args.reuse_graph)
            report = build_index(db, index, encoder, reuse_index=args.reuse_index, reuse_database=ref)
            print(json.dumps({'index': report}), flush=True)
            ref.close()
            ref = None
        vectors = encoder.encode([q.text for q in queries])
        results = {}
        # Run the shipped candidate strategy and a bounded simpler, wider paper strategy.
        for name, kind, papers, candidates in [('current_hybrid_400', 'hybrid', 512, 400),
                                                ('paper_hybrid_400', 'paper', 512, 400),
                                                ('paper_hybrid_800', 'paper', 1024, 800),
                                                ('paper_hybrid_1600', 'paper', 2048, 1600)]:
            if args.only and name != args.only:
                continue
            if kind == 'hybrid':
                engine = HybridIndex(db, index, encoder, profiles=args.window / 'author_profiles',
                                     cross_encoder=None, paper_limit=papers, candidate_limit=candidates,
                                     profile_limit=128, expansion_limit=64, cross_paper_limit=0)
            else:
                engine = SearchIndex(db, index, encoder, paper_limit=papers, candidate_limit=candidates)
            rows = {'hybrid': [], 'lexical': [], 'dense': []}
            timings = []
            print(f'Evaluating {name} on {len(queries)} validation queries.', flush=True)
            for query, vector in zip(queries, vectors):
                before = monotonic()
                found = engine.retrieve(query.text, vector)
                timings.append((monotonic() - before) * 1000)
                for key in rows:
                    rows[key].append((query, found['author_ids'] if key == 'hybrid' else found[key]))
            results[name] = {'paper_limit': papers, 'candidate_limit': candidates,
                             'metrics': {key: summarize(value, known) for key, value in rows.items()},
                             'cached_query_retrieval_latency_ms': {'p50': statistics.median(timings), 'p95': sorted(timings)[int(.95*(len(timings)-1))]}}
            engine.close()
            engine = None
        report = {'scope': 'Inspected validation cohort only; weak future-authorship labels, unjudged other authors, all relevant authors retained. No trained ranker or cross-encoder; cached query embeddings.',
                  'labels_sha256': digest_file(labels), 'source_dataset_sha256': manifest['source_dataset_sha256'],
                  'graph_cutoff_year': manifest['cutoff'], 'package_source_sha256': package_digest(),
                  'results': results}
        write_json(args.out, report)
        print(json.dumps(report, indent=2))
    finally:
        if engine:
            engine.close()
        if ref:
            ref.close()
        db.close()


if __name__ == '__main__':
    main()
