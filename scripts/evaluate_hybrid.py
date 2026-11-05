#!/usr/bin/env python3
"""Evaluate a frozen validation-selected pipeline once on the reserved cohort."""
import argparse
import json
import sys
from pathlib import Path
from time import monotonic

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition, materialize
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.hybrid import HybridIndex


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--freeze', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
if args.out.exists():
    parser.error('Use a new report path; do not overwrite a final evaluation')
frozen = json.loads(args.freeze.read_text())
if package_digest() != frozen['package_source_sha256']:
    raise SystemExit('Package changed after freezing; review and explicitly create a new freeze')
config = frozen['config']
if digest_file(Path(config['dataset']) / 'manifest.json') != frozen['dataset_manifest_sha256']:
    raise SystemExit('Dataset changed after freezing')
models = {}
for name, metadata in frozen['models'].items():
    if digest_file(metadata['path']) != metadata['sha256']:
        raise SystemExit(f'Model changed after freezing: {name}')
    models[name] = json.loads(Path(metadata['path']).read_text())
database = connect(config['graph'])
engine = None
started = monotonic()
try:
    encoder, cross = LocalEncoder(config['encoder']), CrossEncoder(config['cross_encoder'])
    engine = HybridIndex(database, config['index'], encoder, profiles=config['profiles'],
                         cross_encoder=cross, **config['retrieval'])
    rolling = frozen.get('protocol') == 'rolling_inference'
    if rolling:
        manifest = json.loads((Path(config['dataset']) / 'manifest.json').read_text())
        file = Path(config['dataset']) / 'test_ground_truth.jsonl'
        labels_sha = digest_file(file)
        if labels_sha != manifest['files'][file.name] or manifest['graph_cutoff_year'] != engine.anchor_year:
            raise ValueError('Rolling test labels or historical cutoff differ from the sealed cohort')
        source = database.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
        if not source or source[0] != manifest['source_dataset_sha256']:
            raise ValueError('Rolling test provenance differs from the inference snapshot')
        queries = load_queries(file)
        assert_no_leakage(database, [], queries, engine.anchor_year)
        if engine.manifest['content_sha256'] != frozen['inference_content_sha256']:
            raise ValueError('Inference graph changed after freezing')
    else:
        queries, labels_sha = load_partition(config['dataset'], 'test', database)
    for model in models.values():
        if labels_sha in (model['train_labels_sha256'], model['validation_labels_sha256']):
            raise ValueError('Reserved labels overlap training/model-selection labels')
        expected_training = frozen['training_content_sha256'] if rolling else engine.manifest['content_sha256']
        if model['training_content_sha256'] != expected_training:
            raise ValueError('Final graph differs from the trained graph')
        if model['retrieval'] != config['retrieval']:
            raise ValueError('Final retrieval settings differ from the trained model')
    cache = materialize(engine, queries, Path(config['work']) / 'features-reserved-test', labels_sha)
    evaluation = evaluate_rankings(engine, cache, models, seed=config['seed'])
    latency = []
    if not models['learned'].get('use_cross_encoder', True):
        engine.cross_encoder = None
    for query in queries[:20]:
        before = monotonic()
        retrieved = engine.retrieve(query.text)
        from hiresense.ranking.scoring import score_model
        engine.results(query.text, retrieved, score_model(retrieved['features'], models['learned']))
        latency.append((monotonic() - before) * 1000)
    report = {'scope': 'Reserved in-slice 2025–2026 sample; all models frozen before evaluation; not an external field test.',
              'protocol': frozen.get('protocol', 'frozen_history'),
              'training_graph_cutoff_year': models['learned']['graph_cutoff_year'],
              'inference_graph_cutoff_year': engine.anchor_year,
              'freeze_sha256': digest_file(args.freeze), 'package_source_sha256': package_digest(),
              'command': sys.argv, 'config': config, 'selected': frozen['selected'],
              'test_labels_sha256': labels_sha, 'evaluation': evaluation,
              'latency': {'samples': len(latency), 'p50_ms': float(np.quantile(latency, 0.5)),
                          'p95_ms': float(np.quantile(latency, 0.95)),
                          'scope': 'Sequential warm encoding, retrieval, neural scoring when used, reranking and evidence; no throughput claim.'},
              'elapsed_seconds': round(monotonic() - started, 3),
              'limitations': ['Future authorship is a proxy; non-authors are unjudged.',
                              'Same purposefully selected archive, not independently collected data.',
                              'Parent label aggregate counts were previously observed.',
                              'Pretrained model corpus overlap cannot be ruled out.']}
    write_json(args.out, report)
    print(json.dumps({'queries': len(queries), 'metrics': evaluation['metrics'],
                      'coverage': evaluation['coverage'], 'latency': report['latency']}, indent=2))
finally:
    if engine:
        engine.close()
    database.close()
