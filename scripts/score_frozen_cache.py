#!/usr/bin/env python3
"""Rescore the preserved historical candidates with the original evaluator."""
import argparse
import json
from pathlib import Path

import numpy as np
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.evaluation.split import load_queries
from hiresense.graph.build import graph_digest
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('Use a fresh output path')
    manifest = json.loads((a.cache / 'manifest.json').read_text())
    sig = manifest['signature']
    freeze = json.loads((a.frozen_root / 'experiments/lean-freeze-v1.json').read_text())
    if package_digest() != freeze['package_source_sha256']:
        raise ValueError('Historical evaluator package changed')
    for name, checksum in (('lean_ranker.json', 'model_sha256'), ('lean_without_recency.json', 'ablation_sha256')):
        if digest_file(a.frozen_root / 'models' / name) != freeze[checksum]:
            raise ValueError('Frozen model changed')
    labels = a.data / 'test/labels.jsonl'
    if digest_file(a.cache / 'features.npz') != manifest['features_sha256'] or digest_file(labels) != sig['labels_sha256']:
        raise ValueError('Frozen feature cache or labels changed')
    if digest_file(a.frozen_root / 'src/hiresense/retrieval/index.py') != sig['base_implementation_sha256']:
        raise ValueError('Frozen retrieval implementation differs from the feature cache')
    model = json.loads((a.frozen_root / 'models/lean_ranker.json').read_text())
    ablation = json.loads((a.frozen_root / 'models/lean_without_recency.json').read_text())
    db = connect(a.data / 'test/graph.sqlite3')
    if db.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0] != freeze['source_dataset_sha256']:
        raise ValueError('Rebuilt graph source differs from the freeze')
    engine = SearchIndex(db, a.data / 'test/index', LocalEncoder(a.frozen_root / 'models/minilm'), **model['retrieval'])
    try:
        if (engine.manifest['content_sha256'] != sig['content_sha256'] or engine.encoder.signature != sig['encoder_sha256']
                or engine.paper_limit != sig['paper_limit'] or engine.candidate_limit != sig['candidate_limit']):
            raise ValueError('Rebuilt graph/index does not match the preserved feature provenance')
        with np.load(a.cache / 'features.npz', allow_pickle=False) as stored:
            cache = {name: stored[name] for name in stored.files}
        cache['queries'] = load_queries(labels)
        if len(cache['queries']) != manifest['queries']:
            raise ValueError('Frozen query count differs')
        evaluation = evaluate_rankings(engine, cache, {'learned': model, 'without_recency': ablation}, bootstrap_samples=1000)
        write_json(a.out, {'scope': 'Rescoring previously materialized candidates and features, not a fresh retrieval run',
                           'frozen_graph_sha256': sig['graph_sha256'], 'rebuilt_graph_sha256': graph_digest(db),
                           'features_sha256': manifest['features_sha256'], 'evaluation': evaluation})
        print(json.dumps(evaluation['metrics'], indent=2))
    finally:
        engine.close(); db.close()


if __name__ == '__main__':
    main()
