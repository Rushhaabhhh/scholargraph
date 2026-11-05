#!/usr/bin/env python3
"""Freeze validation-selected models and the chronological inference snapshot."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-report', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Use a new freeze file')
    report, plan = json.loads(args.training_report.read_text()), json.loads(args.plan.read_text())
    if report['scope'] != 'Train/validation selection only; reserved test not opened.':
        raise ValueError('Training report does not declare validation-only selection')
    current = package_digest()
    if not report['package_source_sha256_start'] == report['package_source_sha256_end'] == current:
        raise ValueError('Package changed during or after training; repeat training from compatible caches')
    selection = Path(report['selected_model'])
    if digest_file(selection) != report['selected_model_sha256']:
        raise ValueError('Validation-selected model differs from its report')
    model = json.loads(selection.read_text())
    manifest_path = args.dataset / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    index = json.loads((args.index / 'manifest.json').read_text())
    if (manifest['protocol'] != 'rolling_inference' or manifest['plan_sha256'] != digest_file(args.plan)
            or manifest['graph_cutoff_year'] != plan['inference_graph_cutoff_year']
            or model['graph_cutoff_year'] != plan['training_graph_cutoff_year']):
        raise ValueError('Rolling evaluation does not match the predeclared plan')
    if digest_file(args.dataset / 'test_ground_truth.jsonl') != manifest['files']['test_ground_truth.jsonl']:
        raise ValueError('Reserved test artifact differs from its sealed manifest')
    files = {'learned': selection}
    for name in ('reference', 'full', 'without_cross', 'without_graph'):
        files[name] = selection.parent / f'{name}.json'
    models = {name: {'path': str(path), 'sha256': digest_file(path)} for name, path in files.items()}
    for name, item in models.items():
        value = json.loads(Path(item['path']).read_text())
        if value['training_content_sha256'] != model['training_content_sha256']:
            raise ValueError(f'Candidate model {name} was trained on a different graph')
        if value['train_labels_sha256'] != model['train_labels_sha256'] or value['validation_labels_sha256'] != model['validation_labels_sha256']:
            raise ValueError(f'Candidate model {name} used different labels')
    config = {**report['config'], 'graph': str(args.graph), 'index': str(args.index),
              'profiles': str(args.index / 'author_profiles'), 'dataset': str(args.dataset), 'work': str(args.work)}
    frozen = {'protocol': 'rolling_inference', 'selected': report['selected'], 'config': config,
              'plan_sha256': digest_file(args.plan), 'training_report_sha256': digest_file(args.training_report),
              'dataset_manifest_sha256': digest_file(manifest_path), 'models': models,
              'training_content_sha256': model['training_content_sha256'],
              'inference_content_sha256': index['content_sha256'], 'package_source_sha256': current,
              'scope': 'Models selected on 2018-graph validation; snapshot through 2024 used only for subsequent 2025–2026 test inference.'}
    write_json(args.out, frozen)
    print(json.dumps({'selected': frozen['selected'], 'models': models,
                      'freeze_sha256': digest_file(args.out), 'out': str(args.out)}, indent=2))


if __name__ == '__main__':
    main()
