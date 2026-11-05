#!/usr/bin/env python3
"""Evaluate the pre-improvement system on the same frozen reserved queries."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import materialize
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--freeze', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
if args.out.exists():
    parser.error('Use a new report path')
freeze = json.loads(args.freeze.read_text())
if package_digest() != freeze['package_source_sha256']:
    raise ValueError('Package differs from the frozen experiment')
dataset = Path(freeze['config']['dataset'])
manifest = json.loads((dataset / 'manifest.json').read_text())
file = dataset / 'test_ground_truth.jsonl'
if digest_file(dataset / 'manifest.json') != freeze['dataset_manifest_sha256'] or digest_file(file) != manifest['files'][file.name]:
    raise ValueError('Reserved labels differ from the frozen experiment')
queries = load_queries(file)
database = connect('data/processed/phase23/graph.sqlite3')
engine = None
try:
    encoder = LocalEncoder()
    engine = SearchIndex(database, 'data/indexes/phase23', encoder)
    model_path = ROOT / 'models/expert_ranker.json'
    model = json.loads(model_path.read_text())
    if model['training_content_sha256'] != engine.manifest['content_sha256']:
        raise ValueError('Previous model does not match the baseline graph')
    if any(q.year <= 2024 for q in queries):
        raise ValueError('Reserved queries must postdate the new inference graph')
    assert_no_leakage(database, [], queries, engine.anchor_year)
    cache = materialize(engine, queries, Path(freeze['config']['work']) / 'previous-system-test', digest_file(file))
    evaluation = evaluate_rankings(engine, cache, {'learned': model}, seed=freeze['config']['seed'])
    report = {'scope': 'Previous 2018 graph, original retrieval and original model on the same frozen test queries; '
                       'comparison with a 2024 graph changes graph, retrieval and model together.',
              'freeze_sha256': digest_file(args.freeze), 'test_labels_sha256': digest_file(file),
              'package_source_sha256': package_digest(), 'baseline_model_sha256': digest_file(model_path),
              'graph_cutoff_year': engine.anchor_year, 'queries': len(queries), 'evaluation': evaluation,
              'command': sys.argv}
    write_json(args.out, report)
    print(json.dumps({'queries': len(queries), 'metrics': evaluation['metrics'],
                      'coverage': evaluation['coverage']}, indent=2))
finally:
    if engine:
        engine.close()
    database.close()
