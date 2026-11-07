#!/usr/bin/env python3
"""Replay the inspected 2025 benchmark using the frozen code and derived DBLP slice."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'resources/evaluation/reproduction'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path, help='New working directory; use a disk with several GB free')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    frozen = work / 'frozen-code'
    frozen.mkdir()
    with zipfile.ZipFile(ASSETS / 'frozen-source-504ec1.zip') as archive:
        for member in archive.infolist():
            if not (frozen / member.filename).resolve().is_relative_to(frozen):
                raise ValueError('Invalid path in frozen source archive')
        archive.extractall(frozen)
    shutil.copytree(ROOT / 'models/minilm', frozen / 'models/minilm')
    (frozen / 'results').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'resources/evaluation/lean-validation-v1.json', frozen / 'results/lean-validation-v1.json')
    data = work / 'data'
    subprocess.run([sys.executable, str(ROOT / 'scripts/rebuild_lean_data.py'), '--selected-source',
                    str(ASSETS / 'lean-source.xml.gz'), '--manifests', str(ASSETS), '--out', str(data)],
                   cwd=ROOT, check=True)
    report = work / 'replayed-final.json'
    subprocess.run([sys.executable, 'scripts/evaluate_lean.py', '--data', str(data), '--out', str(report)],
                   cwd=frozen, check=True)
    cache_report = work / 'frozen-cache-rescore.json'
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(frozen / 'src')
    subprocess.run([sys.executable, str(ROOT / 'scripts/score_frozen_cache.py'), '--data', str(data),
                    '--cache', str(ASSETS / 'frozen-test-features'), '--frozen-root', str(frozen),
                    '--out', str(cache_report)], cwd=frozen, env=environment, check=True)
    saved = json.loads((ROOT / 'resources/evaluation/lean-final-v1.json').read_text())['evaluation']['metrics']
    replayed = json.loads(report.read_text())['evaluation']['metrics']
    rescored = json.loads(cache_report.read_text())['evaluation']['metrics']
    for label, metrics in (('Fresh retrieval', replayed), ('Frozen feature rescore', rescored)):
        print(f'{label} differences from recorded:')
        for method in ('lexical', 'dense', 'hybrid', 'learned', 'without_recency'):
            differences = {metric: metrics[method][metric] - saved[method][metric] for metric in ('ndcg_at_10', 'mrr')}
            print(f'  {method}: {differences}')
    print(f'Historical replay report: {report}')
    print(f'Frozen feature rescore: {cache_report}')
    print('This cohort was previously inspected; this is not a new independent test.')


if __name__ == '__main__':
    main()
