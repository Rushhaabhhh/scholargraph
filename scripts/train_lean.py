#!/usr/bin/env python3
"""Train and freeze a CPU ranker on separate chronological training and validation graphs."""
import argparse
import json
import shutil
import sys
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import materialize
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.ranking.lambdamart import train_lambdamart
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex, build_index


def load_window(root, name):
    directory = root / name
    manifest = json.loads((directory / 'manifest.json').read_text())
    labels = directory / 'labels.jsonl'
    if manifest['role'] != name or digest_file(labels) != manifest['labels_sha256']:
        raise ValueError('Window labels or role differ from manifest')
    db = connect(directory / 'graph.sqlite3')
    if db.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0] != manifest['source_dataset_sha256']:
        raise ValueError('Window graph provenance differs')
    queries = load_queries(labels)
    assert_no_leakage(db, queries, [], manifest['cutoff'])
    return directory, manifest, db, queries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/processed/lean-v1'))
    parser.add_argument('--work', type=Path, default=Path('data/processed/lean-training-v1'))
    parser.add_argument('--report', type=Path, default=Path('data/research/results/lean-validation-v1.json'))
    parser.add_argument('--freeze', type=Path, default=Path('data/research/experiments/lean-freeze-v1.json'))
    parser.add_argument('--model', type=Path, default=Path('models/lean_ranker.json'))
    args = parser.parse_args()
    if any(p.exists() for p in (args.report, args.freeze, args.model)):
        raise ValueError('Use fresh report, freeze and model paths')
    args.work.mkdir(parents=True, exist_ok=True)
    before, started = package_digest(), monotonic()
    train_dir, train_meta, train_db, train_queries = load_window(args.data, 'train')
    val_dir, val_meta, val_db, val_queries = load_window(args.data, 'validation')
    try:
        if train_meta['source_dataset_sha256'] != val_meta['source_dataset_sha256']:
            raise ValueError('Training and validation sources differ')
        if {q.source_paper_id for q in train_queries} & {q.source_paper_id for q in val_queries}:
            raise ValueError('Training and validation queries overlap')
        encoder = LocalEncoder()
        for directory, db, reference in ((train_dir, train_db, 'train-early'), (val_dir, val_db, 'validation')):
            if not (directory / 'index').exists():
                previous = Path('data/processed/recovery-v2') / reference
                if (previous / 'graph.sqlite3').is_file() and (previous / 'index/manifest.json').is_file():
                    ref = connect(previous / 'graph.sqlite3')
                    try:
                        info = build_index(db, directory / 'index', encoder, reuse_index=previous / 'index', reuse_database=ref)
                    finally:
                        ref.close()
                else:
                    info = build_index(db, directory / 'index', encoder)
                print(json.dumps({'index': str(directory), **info}), flush=True)
        results = {}
        for budget in (800, 1600):
            settings = {'paper_limit': 1024 if budget == 800 else 2048, 'candidate_limit': budget}
            train_engine = SearchIndex(train_db, train_dir / 'index', encoder, **settings)
            val_engine = SearchIndex(val_db, val_dir / 'index', encoder, **settings)
            try:
                train = materialize(train_engine, train_queries, args.work / f'train-{budget}', train_meta['labels_sha256'])
                valid = materialize(val_engine, val_queries, args.work / f'validation-{budget}', val_meta['labels_sha256'])
                metadata = {'retrieval_kind': 'paper', 'retrieval': settings, 'encoder_sha256': encoder.signature,
                            'train_labels_sha256': train_meta['labels_sha256'], 'validation_labels_sha256': val_meta['labels_sha256'],
                            'training_content_sha256': train_engine.manifest['content_sha256'], 'graph_cutoff_year': train_meta['cutoff']}
                model_path = args.work / f'ranker-{budget}.json'
                print(f'Training ranker with {budget} candidates.', flush=True)
                training = train_lambdamart(train, valid, model_path, metadata, seed=42, feature_names=FEATURE_NAMES,
                                              settings=[{'n_estimators': 80, 'num_leaves': 7}])
                model = json.loads(model_path.read_text())
                metrics = evaluate_rankings(val_engine, valid, {'learned': model}, bootstrap_samples=500)
                results[str(budget)] = {'training': training, 'validation': metrics, 'model': str(model_path)}
            finally:
                train_engine.close()
                val_engine.close()
        # The same validation set selects the budget and determines the ablation; the test is unopened.
        selected = max(('800', '1600'), key=lambda b: (results[b]['validation']['metrics']['learned']['ndcg_at_10'],
                                                        results[b]['validation']['metrics']['learned']['mrr'], -int(b)))
        budget = int(selected)
        settings = {'paper_limit': 1024 if budget == 800 else 2048, 'candidate_limit': budget}
        train_engine = SearchIndex(train_db, train_dir / 'index', encoder, **settings)
        val_engine = SearchIndex(val_db, val_dir / 'index', encoder, **settings)
        try:
            train = materialize(train_engine, train_queries, args.work / f'train-{budget}', train_meta['labels_sha256'])
            valid = materialize(val_engine, val_queries, args.work / f'validation-{budget}', val_meta['labels_sha256'])
            chosen = json.loads(Path(results[selected]['model']).read_text())
            ablation_path = args.work / 'without-recency.json'
            metadata = {k: chosen[k] for k in ('retrieval_kind', 'retrieval', 'encoder_sha256', 'train_labels_sha256', 'validation_labels_sha256', 'training_content_sha256', 'graph_cutoff_year')}
            ablation = train_lambdamart(train, valid, ablation_path, metadata, seed=42, feature_names=FEATURE_NAMES,
                                        removed=('matched_recency', 'author_recency'), settings=[{'n_estimators': 80, 'num_leaves': 7}])
            comparison = evaluate_rankings(val_engine, valid, {'learned': chosen, 'without_recency': json.loads(ablation_path.read_text())}, bootstrap_samples=500)
        finally:
            train_engine.close()
            val_engine.close()
        if package_digest() != before:
            raise ValueError('Package changed during training; repeat with frozen code')
        args.model.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(results[selected]['model'], args.model)
        test_ids = Path('data/research/experiments/lean-test-ids.json')
        report = {'scope': 'CPU train and validation only; no final-test labels opened. Future authorship is incomplete relevance supervision.',
                  'data': str(args.data), 'train_queries': len(train_queries), 'validation_queries': len(val_queries),
                  'budgets': results, 'selected_budget': budget, 'ablation_training': ablation, 'selected_comparison': comparison,
                  'ablation_scope': 'Remove explicit recency features while keeping candidates and remaining features fixed; author recency may still influence existing features.',
                  'elapsed_seconds': round(monotonic()-started, 3), 'package_source_sha256': before}
        write_json(args.report, report)
        write_json(args.freeze, {'protocol': 'lean-rolling-v1', 'model': str(args.model), 'model_sha256': digest_file(args.model),
                                'ablation_model': str(ablation_path), 'ablation_sha256': digest_file(ablation_path),
                                'selected_budget': budget, 'source_dataset_sha256': train_meta['source_dataset_sha256'],
                                'validation_report': str(args.report), 'validation_report_sha256': digest_file(args.report), 'package_source_sha256': before,
                                'test_ids_sha256': digest_file(test_ids), 'test_ids': str(test_ids),
                                'train_labels_sha256': train_meta['labels_sha256'], 'validation_labels_sha256': val_meta['labels_sha256']})
        print(json.dumps({'selected_budget': budget, 'validation': comparison['metrics'], 'freeze': str(args.freeze)}, indent=2))
    finally:
        train_db.close()
        val_db.close()


if __name__ == '__main__':
    main()
