#!/usr/bin/env python3
"""Train and select graph-aware hybrid rankers on train/validation only."""
import argparse
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import load_partition, materialize
from hiresense.evaluation.ranking import evaluate_rankings, name_counterfactual
from hiresense.evaluation.split import assert_no_leakage
from hiresense.ranking.lambdamart import train_lambdamart
from hiresense.ranking.scoring import train_ranker
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.hybrid import HybridIndex
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    out, work = Path(config['report']), Path(config['work'])
    if out.exists():
        parser.error('Use a new report path')
    started, code_start = monotonic(), package_digest()
    work.mkdir(parents=True, exist_ok=True)
    models_dir = work / 'models'
    models_dir.mkdir(exist_ok=True)
    database = connect(config['graph'])
    engine = baseline = None
    try:
        train, train_sha = load_partition(config['dataset'], 'train', database)
        valid, valid_sha = load_partition(config['dataset'], 'validation', database)
        encoder, cross = LocalEncoder(config['encoder']), CrossEncoder(config['cross_encoder'])
        engine = HybridIndex(database, config['index'], encoder, profiles=config['profiles'],
                             cross_encoder=cross, **config['retrieval'])
        assert_no_leakage(database, train, valid, engine.anchor_year)
        print(f'Preparing hybrid features for {len(train)} train and {len(valid)} validation queries. No test labels.',
              file=sys.stderr, flush=True)
        training = materialize(engine, train, work / 'features-train', train_sha)
        validation = materialize(engine, valid, work / 'features-validation', valid_sha)
        metadata = {'encoder_sha256': encoder.signature, 'cross_encoder_sha256': cross.signature,
                    'training_content_sha256': engine.manifest['content_sha256'],
                    'train_labels_sha256': train_sha, 'validation_labels_sha256': valid_sha,
                    'graph_cutoff_year': engine.anchor_year, 'retrieval_kind': 'hybrid',
                    'retrieval': config['retrieval'], 'use_cross_encoder': True,
                    'package_source_sha256': code_start}
        reports, models = {}, {}
        print('Training reference classifier and query-grouped hybrid rankers.', file=sys.stderr, flush=True)
        reference_path = models_dir / 'reference.json'
        reports['reference'] = train_ranker({**training, 'features': training['features'][:, :len(FEATURE_NAMES)]},
            {**validation, 'features': validation['features'][:, :len(FEATURE_NAMES)]},
            reference_path, {**metadata, 'use_cross_encoder': False}, seed=config['seed'])
        models['reference'] = json.loads(reference_path.read_text())
        path = models_dir / 'full.json'
        reports['full'] = train_lambdamart(training, validation, path, metadata, seed=config['seed'])
        models['full'] = json.loads(path.read_text())
        for name, removed in (('without_cross', ('cross_max', 'cross_top2', 'cross_observed')),
                              ('without_graph', ('graph_support', 'log_collaborators'))):
            path = models_dir / f'{name}.json'
            reports[name] = train_lambdamart(training, validation, path,
                {**metadata, 'use_cross_encoder': name != 'without_cross'}, seed=config['seed'], removed=removed,
                settings=[reports['full']['parameters']])
            models[name] = json.loads(path.read_text())
        evaluation = evaluate_rankings(engine, validation, models)
        # Prefer cheaper variants for exact metric ties. Selection never reads reserved test labels.
        names = ['reference', 'without_cross', 'without_graph', 'full']
        chosen = max(names, key=lambda name: (evaluation['metrics'][name]['ndcg_at_10'], evaluation['metrics'][name]['mrr']))
        selected = {**models[chosen], 'selection_name': chosen}
        write_json(models_dir / 'selected.json', selected)
        models['learned'] = selected
        evaluation = evaluate_rankings(engine, validation, models)
        baseline = SearchIndex(database, config['index'], encoder,
                               paper_limit=config['retrieval']['paper_limit'], candidate_limit=config['retrieval']['candidate_limit'])
        plain_cache = materialize(baseline, valid, work / 'plain-validation', valid_sha)
        plain = evaluate_rankings(baseline, plain_cache, {})
        fairness = name_counterfactual(engine, selected, valid[:8])
        report = {'scope': 'Train/validation selection only; reserved test not opened.', 'config': config,
                  'config_sha256': digest_file(args.config), 'command': sys.argv,
                  'package_source_sha256_start': code_start, 'package_source_sha256_end': package_digest(),
                  'environment': {'python': platform.python_version(), 'lightgbm': version('lightgbm'),
                                  'onnxruntime': version('onnxruntime'), 'scikit-learn': version('scikit-learn')},
                  'queries': {'train': len(train), 'validation': len(valid)}, 'training': reports,
                  'validation': evaluation, 'plain_retrieval_validation': plain,
                  'name_counterfactual': fairness, 'selected': chosen,
                  'selected_model': str(models_dir / 'selected.json'),
                  'selected_model_sha256': digest_file(models_dir / 'selected.json'),
                  'feature_ablation_scope': 'Identical hybrid candidate pools and labels. Without-graph removes explicit graph '
                      'features, not graph candidate generation; without-cross removes only pair-score features.',
                  'limitations': ['Authorship is weak expertise supervision; sampled non-authors are unjudged.',
                                  'Purposeful venue history is not representative of all DBLP.',
                                  'Pretrained encoder and cross-encoder overlap cannot be ruled out.'],
                  'elapsed_seconds': round(monotonic() - started, 3)}
        write_json(out, report)
        print(json.dumps({'selected': chosen, 'validation': evaluation['metrics'],
                          'training': reports, 'report': str(out)}, indent=2))
    finally:
        if engine:
            engine.close()
        if baseline:
            baseline.close()
        database.close()


if __name__ == '__main__':
    main()
