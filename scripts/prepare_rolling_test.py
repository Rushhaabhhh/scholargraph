#!/usr/bin/env python3
"""Seal an unscored chronological test sample against its inference snapshot."""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, title_key, write_json
from hiresense.db import connect
from hiresense.evaluation.split import assert_no_leakage, load_queries

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan', required=True, type=Path)
parser.add_argument('--graph', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
if args.out.exists() or not args.graph.is_file():
    parser.error('Use an existing graph and new output directory')
plan = json.loads(args.plan.read_text())
parent = Path(plan['reserved_parent'])
parent_manifest = json.loads((parent / 'manifest.json').read_text())
file = parent / 'test_ground_truth.jsonl'
if digest_file(file) != parent_manifest['files'][file.name]:
    raise SystemExit('Reserved parent labels changed')
database = connect(args.graph)
try:
    cutoff = int(database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()[0])
    if cutoff != plan['inference_graph_cutoff_year']:
        raise ValueError('Inference graph does not match the predeclared plan')
    queries = load_queries(file)
    eligible = [q for q in queries if not database.execute(
        'SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1', (q.source_paper_id, title_key(q.text))).fetchone()]
    chosen = sorted(eligible, key=lambda q: (hashlib.sha256(f"{plan['seed']}:{q.query_id}".encode()).digest(), q.query_id))[:plan['sample_size']]
    if len(chosen) != plan['sample_size'] or any(q.year not in plan['reserved_label_years'] for q in chosen):
        raise ValueError('Insufficient eligible reserved queries or invalid years')
    assert_no_leakage(database, [], chosen, cutoff)
    args.out.mkdir(parents=True)
    output = args.out / 'test_ground_truth.jsonl'
    output.write_text(''.join(json.dumps(asdict(q), ensure_ascii=False, sort_keys=True) + '\n' for q in chosen))
    manifest = {'protocol': 'rolling_inference', 'plan_sha256': digest_file(args.plan),
                'graph_cutoff_year': cutoff, 'parent_manifest_sha256': digest_file(parent / 'manifest.json'),
                'parent_test_sha256': digest_file(file), 'parent_count': len(queries),
                'excluded_title_or_key_overlap': len(queries) - len(eligible),
                'test_count': len(chosen), 'remaining_eligible_unscored': len(eligible) - len(chosen),
                'files': {'test_ground_truth.jsonl': digest_file(output)},
                'source_dataset_sha256': database.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0]}
    write_json(args.out / 'manifest.json', manifest)
    print(json.dumps(manifest, indent=2))
finally:
    database.close()
