#!/usr/bin/env python3
"""Evaluate top-ten responses from a running API against existing temporal labels.

The relevance labels are future authorship proxies, not human hiring judgments.
The endpoint should be the frontend's /api boundary or the backend's root URL.
"""
import argparse
import hashlib
import json
import math
import random
import sqlite3
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data, {'Content-Type': 'application/json'},
                                     method='GET' if data is None else 'POST')
    with urllib.request.urlopen(request, timeout=80) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', required=True, help='API base URL, e.g. http://127.0.0.1:3017/api')
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=10, help='Number of ranked results to request, from 10 to 100')
    parser.add_argument('--sample-size', type=int, help='Evaluate a deterministic subset of the supplied labels')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--graph', type=Path, help='Optional serving graph for the labelled-author history denominator')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a new report path; existing reports are not overwritten')
    raw = args.labels.read_bytes()
    labels = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if not labels:
        raise ValueError('No query labels found')
    if not 10 <= args.limit <= 100:
        raise ValueError('Limit must be between 10 and 100')
    total_labels = len(labels)
    if args.sample_size is not None:
        if not 1 <= args.sample_size <= len(labels):
            raise ValueError('Sample size must be between 1 and the number of labels')
        selected = sorted(random.Random(args.seed).sample(range(len(labels)), args.sample_size))
        labels = [labels[index] for index in selected]
    known = None
    if args.graph:
        ids = list({identifier for query in labels for identifier in query['relevant_author_ids']})
        known = set()
        with sqlite3.connect(args.graph.resolve().as_uri() + '?mode=ro', uri=True) as graph:
            for offset in range(0, len(ids), 500):
                batch = ids[offset:offset + 500]
                placeholders = ','.join('?' for _ in batch)
                known.update(row[0] for row in graph.execute(f'SELECT id FROM authors WHERE id IN ({placeholders})', batch))
    health = request_json(args.api.rstrip('/') + '/health')
    rows = []
    started = time.monotonic()
    for index, query in enumerate(labels, 1):
        begin = time.monotonic()
        relevant = set(query['relevant_author_ids'])
        try:
            payload = {'query': query['text'], 'limit': args.limit, 'recency_preference': 'any', 'since_year': None}
            data = request_json(args.api.rstrip('/') + '/search', payload)
            hits = [rank for rank, result in enumerate(data['results'], 1) if result['person_id'] in relevant]
            hits10 = [rank for rank in hits if rank <= 10]
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant)) + 1))
            dcg = sum(1 / math.log2(rank + 1) for rank in hits10)
            rows.append({'query_id': query['query_id'], 'query': query['text'], 'year': query['year'],
                         'label_author_ids': query['relevant_author_ids'], 'known_author_count': len(relevant & known) if known is not None else None,
                         'hit_ranks': hits, 'hit_ranks_at_10': hits10, 'returned_count': len(data['results']),
                         'ndcg_at_10': dcg / ideal if ideal else 0.0,
                         'reciprocal_rank_at_10': 1 / hits10[0] if hits10 else 0.0,
                         'reciprocal_rank_at_limit': 1 / hits[0] if hits else 0.0,
                         'retrieval_query': data['retrieval_query'], 'provider': data['understanding']['provider'],
                         'fallback_reason': data['understanding']['fallback_reason'],
                         'results': [{'person_id': result['person_id'], 'name': result['name'], 'score': result['score'],
                                      'paper_ids': [paper['paper_id'] for paper in result['evidence']],
                                      'claims': len(result['claims']),
                                      'unsupported_claims': sum(not claim['supported'] for claim in result['claims'])}
                                     for result in data['results'][:10]],
                         'labelled_hits_after_10': [{'rank': rank, 'person_id': data['results'][rank-1]['person_id'],
                                                     'name': data['results'][rank-1]['name']} for rank in hits if rank > 10],
                         'latency_ms': (time.monotonic() - begin) * 1000})
        except (OSError, ValueError, KeyError) as error:
            rows.append({'query_id': query['query_id'], 'error': f'{type(error).__name__}: {error}',
                         'label_author_ids': query['relevant_author_ids'], 'known_author_count': len(relevant & known) if known is not None else None,
                         'ndcg_at_10': 0.0, 'reciprocal_rank_at_10': 0.0, 'reciprocal_rank_at_limit': 0.0})
        if index % 50 == 0 or index == len(labels):
            print(f'Processed {index}/{len(labels)} queries', flush=True)
    successful = [row for row in rows if 'error' not in row]
    latencies = sorted(row['latency_ms'] for row in successful)
    relevant_count = sum(len(set(row['label_author_ids'])) for row in rows)
    known_count = sum(row['known_author_count'] for row in rows) if known is not None else None
    hits_at_limit = sum(len(row.get('hit_ranks', [])) for row in rows)
    report = {'scope': 'Stateless ranked API responses with empty decisions; future-author labels are incomplete proxy judgments. Recheck whether the labels have already been inspected.',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'api': args.api, 'health': health,
              'labels': str(args.labels), 'labels_sha256': hashlib.sha256(raw).hexdigest(),
              'labels_total': total_labels, 'sample_seed': args.seed if args.sample_size is not None else None,
              'result_limit': args.limit, 'graph_for_history': str(args.graph) if args.graph else None,
              'queries': len(labels), 'successful': len(successful), 'errors': len(rows) - len(successful),
              'metrics_all_queries': {'ndcg_at_10': statistics.fmean(row['ndcg_at_10'] for row in rows),
                                      'mrr_at_10': statistics.fmean(row['reciprocal_rank_at_10'] for row in rows),
                                      'mrr_at_limit': statistics.fmean(row['reciprocal_rank_at_limit'] for row in rows),
                                      'hit_at_1': sum(row.get('hit_ranks_at_10', [])[:1] == [1] for row in rows) / len(rows),
                                      'hit_at_10': sum(bool(row.get('hit_ranks_at_10')) for row in rows) / len(rows),
                                      'hit_at_limit': sum(bool(row.get('hit_ranks')) for row in rows) / len(rows),
                                      'labelled_author_instances': relevant_count,
                                      'known_author_instances': known_count,
                                      'labelled_author_hits_at_limit': hits_at_limit,
                                      'labelled_author_recall_at_limit_all': hits_at_limit / relevant_count if relevant_count else None,
                                      'labelled_author_recall_at_limit_known': hits_at_limit / known_count if known_count else None},
              'understanding_providers': dict(Counter(row['provider'] for row in successful)),
              'latency_ms': {'p50': statistics.median(latencies), 'p95': latencies[round(.95 * (len(latencies) - 1))]} if latencies else None,
              'elapsed_seconds': round(time.monotonic() - started, 2), 'per_query': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('queries', 'successful', 'errors', 'metrics_all_queries', 'understanding_providers', 'latency_ms', 'elapsed_seconds')}, indent=2))


if __name__ == '__main__':
    main()
