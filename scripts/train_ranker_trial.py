#!/usr/bin/env python3
"""Reproduce a bounded ranker trial from the prepared historical feature caches."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file
from hiresense.evaluation.split import load_queries
from hiresense.ranking.lambdamart import train_lambdamart
from hiresense.ranking.scoring import cache_metrics, score_model
from hiresense.retrieval.index import FEATURE_NAMES


def load(role):
    directory = Path('data/processed/lean-training-v1') / (role + '-800')
    manifest = json.loads((directory / 'manifest.json').read_text())
    labels = Path('data/processed/lean-v1') / role / 'labels.jsonl'
    signature = manifest['signature']
    if (digest_file(directory / 'features.npz') != manifest['features_sha256']
            or digest_file(labels) != signature['labels_sha256']
            or digest_file('src/hiresense/retrieval/index.py') != signature['base_implementation_sha256']
            or tuple(signature['features']) != FEATURE_NAMES):
        raise ValueError('Training cache, labels, or retrieval implementation changed')
    with np.load(directory / 'features.npz', allow_pickle=False) as stored:
        cache = {name: stored[name] for name in stored.files}
    cache['queries'] = load_queries(labels)
    if len(cache['queries']) != manifest['queries']:
        raise ValueError('Cache query count mismatch')
    return cache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='New directory for trained experimental models')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('Use a new output directory')
    args.out.mkdir(parents=True)
    train, validation = load('train'), load('validation')
    base = json.loads(Path('models/hybrid_ranker.json').read_text())
    metadata = {key: base[key] for key in ('retrieval_kind', 'retrieval', 'encoder_sha256', 'train_labels_sha256',
                                            'validation_labels_sha256', 'training_content_sha256', 'graph_cutoff_year')}
    print('Current:', cache_metrics(validation, score_model(validation['features'], base)), flush=True)
    for name, settings, removed in (
        ('candidate', [{'n_estimators': 160, 'num_leaves': 7}, {'n_estimators': 160, 'num_leaves': 15}], ()),
        ('without-collaborator-count', [{'n_estimators': 80, 'num_leaves': 7}], ('log_collaborators',))):
        result = train_lambdamart(train, validation, args.out / f'{name}.json', metadata, seed=42,
                                  feature_names=FEATURE_NAMES, settings=settings, removed=removed)
        print(name, json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
