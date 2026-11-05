"""Reproducible graph, identity, retrieval, training and held-out evaluation run."""

import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from time import monotonic

import numpy as np

from ..data.artifacts import digest_file, package_digest, write_json
from ..db import connect, initialize
from ..graph.build import build_context_graph
from ..graph.resolution import resolve_records
from ..ranking.scoring import train_ranker
from ..ranking.service import search
from ..retrieval.encoder import LocalEncoder
from ..retrieval.index import FEATURE_GROUPS, FEATURE_NAMES, SearchIndex, build_index
from .features import load_partition, materialize
from .ranking import evaluate_rankings, name_counterfactual
from .resolution import evaluate_resolution
from .split import assert_no_leakage


def train_from_dataset(engine, dataset, work, model_path, seed=42, ablate=None, parameters=None):
    train, train_sha = load_partition(dataset, 'train', engine.database)
    validation, validation_sha = load_partition(dataset, 'validation', engine.database)
    assert_no_leakage(engine.database, train, validation, engine.anchor_year)
    training = materialize(engine, train, Path(work) / 'features-train', train_sha)
    validating = materialize(engine, validation, Path(work) / 'features-validation', validation_sha)
    metadata = {'encoder_sha256': engine.encoder.signature, 'training_content_sha256': engine.manifest['content_sha256'],
                'train_labels_sha256': train_sha, 'validation_labels_sha256': validation_sha,
                'graph_cutoff_year': engine.anchor_year, 'paper_limit': engine.paper_limit,
                'candidate_limit': engine.candidate_limit, 'feature_version': 1}
    removed = FEATURE_GROUPS.get(ablate, ())
    selected = [index for index, name in enumerate(FEATURE_NAMES) if name not in removed]
    return train_ranker(training, validating, model_path, metadata, seed, selected, parameters)


def evaluate_from_dataset(engine, dataset, work, model_path, role='test'):
    queries, labels_sha = load_partition(dataset, role, engine.database)
    model = json.loads(Path(model_path).read_text())
    if model['training_content_sha256'] != engine.manifest['content_sha256']:
        raise ValueError('Evaluation graph differs from training graph; use search for inference on a new graph')
    if labels_sha in (model['train_labels_sha256'], model['validation_labels_sha256']) and role == 'test':
        raise ValueError('Test labels overlap model selection labels')
    cache = materialize(engine, queries, Path(work) / f'features-{role}', labels_sha)
    return evaluate_rankings(engine, cache, {'learned': model})


def run_ml_experiment(config_path):
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    dataset, work, index_dir = Path(config['dataset']), Path(config['work']), Path(config['index'])
    model_dir, report_file = Path(config['models']), Path(config['report'])
    if report_file.exists():
        raise ValueError('Results report already exists; choose new experiment paths to preserve prior results')
    started = monotonic()
    work.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    graph_file = work / 'graph.sqlite3'
    if not graph_file.exists():
        source = connect(dataset / 'graph.sqlite3')
        destination = connect(graph_file)
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
    database = connect(graph_file)
    engine = None
    try:
        initialize(database)
        manifest = json.loads((dataset / 'manifest.json').read_text())
        actual = database.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
        if actual is None or actual[0] != manifest['source_dataset_sha256']:
            raise ValueError('Existing experiment graph belongs to a different source dataset')
        graph = build_context_graph(database)
        repeated_graph = build_context_graph(database)
        if graph['sha256'] != repeated_graph['sha256']:
            raise ValueError('Graph rebuild is not idempotent')
        print(f"Verified {graph['context_edges']} graph edges; resolving noisy identities.", file=sys.stderr, flush=True)
        resolution = resolve_records(database, config['noise'], **config['resolution'])
        resolution['evaluation'] = evaluate_resolution(database, Path(config['noise']).with_suffix('.truth.jsonl'))
        resolution['observation_sha256'] = digest_file(config['noise'])
        resolution['truth_sha256'] = digest_file(Path(config['noise']).with_suffix('.truth.jsonl'))
        print('Entity resolution evaluated; preparing retrieval.', file=sys.stderr, flush=True)
        encoder = LocalEncoder(config['encoder'])
        index_report = build_index(database, index_dir, encoder) if not index_dir.exists() else {'reused_verified_artifact': str(index_dir)}
        engine = SearchIndex(database, index_dir, encoder, **config['retrieval'])
        selected = train_from_dataset(engine, dataset, work, model_dir / 'expert_ranker.json', config['seed'])
        main = json.loads((model_dir / 'expert_ranker.json').read_text())
        models = {'learned': main}
        ablations = {}
        for group in FEATURE_GROUPS:
            path = model_dir / f'without-{group}.json'
            ablations[group] = train_from_dataset(engine, dataset, work, path, config['seed'], group, selected['parameters'])
            models[f'without_{group}'] = json.loads(path.read_text())
        # The test labels are first opened after all model fitting and validation selection finish.
        print('Models and retrained ablations frozen; opening held-out test labels.', file=sys.stderr, flush=True)
        queries, labels_sha = load_partition(dataset, 'test', database)
        if labels_sha in (main['train_labels_sha256'], main['validation_labels_sha256']):
            raise ValueError('Test and model-selection label hashes overlap')
        cache = materialize(engine, queries, work / 'features-test', labels_sha)
        evaluation = evaluate_rankings(engine, cache, models, seed=config['seed'])
        fairness = name_counterfactual(engine, main, queries[:16])
        latencies = []
        for query in queries[:40]:
            before = monotonic()
            search(engine, query.text, main)
            latencies.append((monotonic() - before) * 1000)
        report = {
            'config': config, 'config_sha256': digest_file(config_path), 'package_source_sha256': package_digest(),
            'command': ['.venv/bin/python', '-m', 'hiresense.cli', 'ml-benchmark', '--config', str(config_path)],
            'environment_variables': {'PYTHONPATH': 'src'},
            'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                            'packages': {name: version(name) for name in ('numpy', 'scikit-learn', 'onnxruntime', 'tokenizers')}},
            'graph': graph, 'resolution': resolution, 'index': index_report,
            'trained_model': selected, 'ablations': ablations, 'test': evaluation, 'name_counterfactual': fairness,
            'latency': {'samples': len(latencies), 'p50_ms': float(np.percentile(latencies, 50)),
                        'p95_ms': float(np.percentile(latencies, 95)),
                        'scope': 'Sequential warm queries on this local slice; includes encoding, retrieval, reranking and evidence. No throughput claim.'},
            'model_files': {path.name: digest_file(path) for path in sorted(model_dir.glob('*.json'))},
            'bundled_model_bytes': sum(path.stat().st_size for path in model_dir.rglob('*') if path.is_file()),
            'source_evaluation_limits': ['Synthetic known-identity linkage does not measure open-world identity clustering.',
                                        'Source-order DBLP slice is not representative; missing historical authors remain in the relevance denominator.',
                                        'Pretrained encoder training-corpus overlap cannot be independently excluded.',
                                        'Future authorship labels are an expertise proxy; non-authors are unjudged negatives.'],
            'elapsed_seconds': round(monotonic() - started, 3),
        }
        write_json(report_file, report)
        return report
    finally:
        if engine:
            engine.close()
        database.close()
