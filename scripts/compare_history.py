#!/usr/bin/env python3
"""Compare historical author coverage on exactly the same validation queries."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import package_digest, title_key, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition
from hiresense.evaluation.split import assert_no_leakage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-graph', type=Path, required=True)
    parser.add_argument('--expanded-graph', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or not args.baseline_graph.is_file() or not args.expanded_graph.is_file():
        parser.error('Graphs must exist and output must be a new path')
    first, second = connect(args.baseline_graph), connect(args.expanded_graph)
    try:
        cutoffs = [db.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone() for db in (first, second)]
        if not all(cutoffs) or cutoffs[0][0] != cutoffs[1][0]:
            raise ValueError('Graph cutoff years must be identical')
        cutoff = int(cutoffs[0][0])
        for db in (first, second):
            assert_no_leakage(db, [], [], cutoff)
        queries, labels_hash = load_partition(args.dataset, 'validation', first)
        # Preserve a fixed cohort. Remove any query whose key or title appears in either graph.
        safe = []
        for query in queries:
            if any(db.execute('SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1',
                              (query.source_paper_id, title_key(query.text))).fetchone() for db in (first, second)):
                continue
            safe.append(query)
        rows = []
        for name, database in (('baseline', first), ('expanded', second)):
            known = {row[0] for row in database.execute('SELECT id FROM authors')}
            total = sum(len(set(q.relevant_author_ids)) for q in safe)
            covered = sum(len(set(q.relevant_author_ids) & known) for q in safe)
            rows.append({'graph': name, 'papers': database.execute('SELECT COUNT(*) FROM papers').fetchone()[0],
                         'authors': len(known), 'relevant_authors': total, 'relevant_with_history': covered,
                         'author_history_coverage': covered / total if total else None,
                         'queries_with_history': sum(bool(set(q.relevant_author_ids) & known) for q in safe)})
        report = {'scope': 'Same fixed validation labels on both frozen graphs; not final test. Source-order expansion is not representative.',
                  'cutoff_year': cutoff, 'validation_labels_sha256': labels_hash, 'queries': len(safe),
                  'excluded_for_graph_title_or_key_overlap': len(queries) - len(safe),
                  'query_ids_sha256': hashlib.sha256('\n'.join(q.query_id for q in safe).encode()).hexdigest(),
                  'comparison': rows, 'package_source_sha256': package_digest(), 'command': sys.argv}
        write_json(args.out, report)
        print(json.dumps(report, indent=2))
    finally:
        first.close()
        second.close()


if __name__ == '__main__':
    main()
