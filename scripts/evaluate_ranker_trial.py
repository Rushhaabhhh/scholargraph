#!/usr/bin/env python3
"""Compare frozen rankers on a new, seeded 2025 future-authorship sample.

Development diagnostic, not a human relevance benchmark. Does not promote models.
"""
import argparse
import hashlib
import json
import random
import sqlite3
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.api.runtime import Backend
from hiresense.assistant.providers import deterministic_intent
from hiresense.data.artifacts import digest_file, title_key, write_json
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.models import GroundTruthQuery
from hiresense.ranking.scoring import score_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--ablation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=300)
    parser.add_argument('--seed', type=int, default=17041)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a new output path')
    started = time.monotonic()
    model_paths = {'current': Path('models/hybrid_ranker.json'), 'candidate': args.candidate,
                   'without_collaborator_count': args.ablation}
    hashes = {name: digest_file(path) for name, path in model_paths.items()}
    models = {name: json.loads(path.read_text()) for name, path in model_paths.items()}
    for model in models.values():
        if model['retrieval'] != models['current']['retrieval'] or model['encoder_sha256'] != models['current']['encoder_sha256']:
            raise ValueError('Models must share candidate retrieval and encoder')
    # Model hashes are printed before reading the sampled evaluation labels.
    print('Frozen model hashes: ' + json.dumps(hashes), flush=True)
    source = sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    import tempfile
    with tempfile.TemporaryDirectory(prefix='scholar-rank-eval-') as temporary:
        backend = Backend.load('resources/experiments/backend.json', session_db_override=Path(temporary) / 'sessions.sqlite')
        try:
            db, engine = backend.database, backend.engine
            excluded = set(json.loads(Path('resources/experiments/lean-test-ids.json').read_text())['source_paper_ids'])
            prior = [q for split in ('train', 'validation') for q in load_queries(Path('data/processed/lean-v1') / split / 'labels.jsonl')]
            excluded.update(q.source_paper_id for q in prior)
            excluded_titles = {title_key(q.text) for q in prior}
            rows = list(source.execute('SELECT id,title,year,title_key FROM papers WHERE year=2025 ORDER BY id'))
            random.Random(args.seed).shuffle(rows)
            queries, seen_titles = [], set()
            for row in rows:
                key = title_key(row['title'])
                if row['id'] in excluded or not key or key in excluded_titles or key in seen_titles:
                    continue
                if db.execute('SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1', (row['id'], key)).fetchone():
                    continue
                authors = tuple(a[0] for a in source.execute('SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position', (row['id'],)))
                if not authors:
                    continue
                queries.append(GroundTruthQuery(row['id'], row['title'], row['id'], row['year'], authors))
                seen_titles.add(key)
                if len(queries) == args.samples:
                    break
            if len(queries) != args.samples:
                raise ValueError('Insufficient eligible queries')
            assert_no_leakage(db, queries, [], 2024)
            unique_targets = {identifier for query in queries for identifier in query.relevant_author_ids}
            identity_checked = identity_mismatches = 0
            for identifier in unique_targets:
                source_author = source.execute('SELECT source_key FROM authors WHERE id=?', (identifier,)).fetchone()
                graph_author = db.execute('SELECT source_key FROM authors WHERE id=?', (identifier,)).fetchone()
                if source_author and graph_author:
                    identity_checked += 1
                    identity_mismatches += source_author['source_key'] != graph_author['source_key']
            methods = ['lexical', 'dense', 'hybrid', *models]
            results = {name: [] for name in methods}
            total = known = hits = available = 0
            timings, abstained = [], 0
            for n, query in enumerate(queries, 1):
                # Match the deterministic serving intent and date filter, while reusing
                # the identical candidate set for every ranker and ablation.
                start = time.monotonic()
                intent = deterministic_intent(query.text)
                text = ' '.join(intent.topics)
                cutoff = intent.since_year
                if cutoff is None and intent.recency_preference == 'recent':
                    cutoff = max(1, engine.anchor_year - 5)
                retrieved = engine.retrieve(text, since_year=cutoff)
                timings.append((time.monotonic() - start) * 1000)
                ids = np.asarray(retrieved['author_ids'], dtype=np.int64)
                relevant = set(query.relevant_author_ids)
                known_ids = relevant & engine.authors.keys()
                total += len(relevant); known += len(known_ids); hits += len(relevant & set(ids.tolist())); available += bool(known_ids)
                if not retrieved['lexical']:
                    abstained += 1
                    orders = {name: [] for name in methods}
                else:
                    orders = {'lexical': retrieved['lexical'], 'dense': retrieved['dense'], 'hybrid': ids.tolist()}
                    for name, model in models.items():
                        scores = score_model(retrieved['features'], model)
                        orders[name] = ids[np.lexsort((ids, -scores))].tolist()
                for name, order in orders.items():
                    # MRR@10, consistently truncated for every method.
                    results[name].append(ranking_metrics(order[:10], relevant))
                if n % 50 == 0:
                    print(f'Evaluated {n}/{len(queries)}', flush=True)
            metrics = {name: {key: float(np.mean([r[key] for r in rows])) for key in ('ndcg_at_10', 'mrr')}
                       for name, rows in results.items()}
            rng = np.random.default_rng(args.seed)
            paired = np.asarray([a['ndcg_at_10'] - b['ndcg_at_10'] for a, b in zip(results['candidate'], results['current'])])
            samples = rng.integers(0, len(paired), size=(5000, len(paired)))
            interval = np.quantile(paired[samples].mean(axis=1), [0.025, 0.975]).tolist()
            label_bytes = ''.join(json.dumps(asdict(q), sort_keys=True, ensure_ascii=False) + '\n' for q in queries).encode()
            report = {'scope': 'Seeded 2025 future-authorship queries from the same curated source, excluding the prior 500-query test and known training and validation IDs and titles. Exposure in other earlier experiments was not exhaustively audited; this cohort is now inspected. Labels are incomplete, not human relevance or hiring accuracy.',
                      'command': sys.argv, 'seed': args.seed, 'queries': len(queries), 'label_sha256': hashlib.sha256(label_bytes).hexdigest(),
                      'query_ids': [q.query_id for q in queries], 'graph_cutoff_year': 2024,
                      'graph_content_sha256': engine.manifest['content_sha256'], 'graph_papers': len(engine.papers),
                      'source_database_sha256': digest_file('data/processed/lean-v1/source.sqlite3'),
                      'model_sha256': hashes, 'metrics_at_10': metrics,
                      'coverage': {'relevant_author_instances': total, 'known_author_instances': known,
                                   'queries_with_known_author': available, 'candidate_hits': hits,
                                   'recall_all': hits/max(total, 1), 'recall_known': hits/max(known, 1),
                                   'no_lexical_evidence_abstentions': abstained},
                      'identity_consistency': {'unique_known_target_ids_checked': identity_checked,
                                               'source_key_disagreements': identity_mismatches},
                      'candidate_vs_current': {'ndcg_at_10_delta': float(paired.mean()), 'paired_bootstrap_95pct': interval,
                                               'queries_improved': int((paired > 0).sum()), 'queries_worse': int((paired < 0).sum()),
                                               'queries_tied': int((paired == 0).sum())},
                      'latency_ms': {'p50': float(np.percentile(timings, 50)), 'p95': float(np.percentile(timings, 95)),
                                     'scope': 'Warm retrieval including encoding; excludes ranker, grounding and HTTP.'},
                      'elapsed_seconds': round(time.monotonic() - started, 2),
                      'limitations': ['Same curated source and topic distribution as earlier experiments.',
                                      'Graph and labels came from different derived slices; source-key agreement is not a human identity audit.',
                                      'Exact IDs and normalized titles were checked, not semantic duplicates.',
                                      'Ablation removes only collaborator-count feature; other graph and recency signals remain.',
                                      'No explicit relative-year correction, injection handling, evidence verification or decisions in this ranking diagnostic.']}
            write_json(args.out, report)
            print(json.dumps({k: report[k] for k in ('metrics_at_10', 'coverage', 'candidate_vs_current', 'latency_ms', 'elapsed_seconds')}, indent=2))
        finally:
            backend.close()
            source.close()


if __name__ == '__main__':
    main()
