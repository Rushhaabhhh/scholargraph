#!/usr/bin/env python3
"""Paired comparison of frozen systems on the same already-scored reserved queries."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import load_queries
from hiresense.ranking.scoring import score_model

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--freeze', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
parser.add_argument('--bootstrap', type=int, default=1000)
args = parser.parse_args()
if args.out.exists() or args.bootstrap < 100:
    parser.error('Use a new output path and at least 100 bootstrap samples')
freeze = json.loads(args.freeze.read_text())
if package_digest() != freeze['package_source_sha256']:
    raise ValueError('Package differs from frozen experiment')
dataset = Path(freeze['config']['dataset'])
labels = dataset / 'test_ground_truth.jsonl'
manifest = json.loads((dataset / 'manifest.json').read_text())
if digest_file(dataset / 'manifest.json') != freeze['dataset_manifest_sha256'] or digest_file(labels) != manifest['files'][labels.name]:
    raise ValueError('Reserved labels differ from frozen manifest')
queries = load_queries(labels)
work = Path(freeze['config']['work'])


def compute(directory, model_path, expected_model_hash):
    metadata = json.loads((directory / 'manifest.json').read_text())
    if metadata['signature']['labels_sha256'] != digest_file(labels):
        raise ValueError('Cached features do not use the same reserved queries')
    if digest_file(directory / 'features.npz') != metadata['features_sha256']:
        raise ValueError('Feature cache checksum mismatch')
    if digest_file(model_path) != expected_model_hash:
        raise ValueError('Model checksum mismatch')
    model = json.loads(Path(model_path).read_text())
    with np.load(directory / 'features.npz', allow_pickle=False) as cache:
        values = score_model(cache['features'], model)
        if len(cache['offsets']) != len(queries) + 1:
            raise ValueError('Feature offsets do not match reserved queries')
        rows = []
        for i, query in enumerate(queries):
            start, end = cache['offsets'][i:i + 2]
            ids = cache['author_ids'][start:end]
            ranked = ids[np.lexsort((ids, -values[start:end]))].tolist()
            rows.append(ranking_metrics(ranked, set(query.relevant_author_ids)))
    return rows


learned = freeze['models']['learned']
new = compute(work / 'features-reserved-test', learned['path'], learned['sha256'])
previous_report = json.loads((ROOT / 'results/hybrid-final-previous-baseline.json').read_text())
if previous_report['freeze_sha256'] != digest_file(args.freeze):
    raise ValueError('Previous-system report uses a different freeze')
old_model = ROOT / 'models/expert_ranker.json'
old = compute(work / 'previous-system-test', old_model, previous_report['baseline_model_sha256'])
rng = np.random.default_rng(freeze['config']['seed'])
indices = rng.integers(0, len(queries), size=(args.bootstrap, len(queries)))
metrics = {}
for key in ('ndcg_at_10', 'mrr'):
    baseline = np.asarray([r[key] for r in old])
    improved = np.asarray([r[key] for r in new])
    delta = improved - baseline
    metrics[key] = {'previous': float(baseline.mean()), 'new': float(improved.mean()),
                    'mean_delta': float(delta.mean()),
                    'paired_bootstrap_95pct': np.quantile(delta[indices].mean(axis=1), [0.025, 0.975]).tolist()}
report = {'scope': 'Frozen end-to-end systems on identical in-slice test queries; graph cutoff, data, retrieval and model change together.',
          'limitation': 'Bootstrap resamples query titles, not independent research fields; pretrained overlap and weak authorship labels remain.',
          'queries': len(queries), 'freeze_sha256': digest_file(args.freeze), 'test_sha256': digest_file(labels),
          'bootstrap_samples': args.bootstrap, 'seed': freeze['config']['seed'], 'metrics': metrics, 'command': sys.argv}
write_json(args.out, report)
print(json.dumps(report, indent=2))
