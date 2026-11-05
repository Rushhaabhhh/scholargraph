#!/usr/bin/env python3
"""Verify the distributable source/assets with an existing prepared environment."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import write_json

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--candidate-model', type=Path, help='Test a candidate as the default model in the temporary copy')
args = parser.parse_args()
if args.out.exists():
    raise SystemExit('Use a new report path')
with tempfile.TemporaryDirectory(prefix='hiresense-backend-clean-') as temporary:
    clean = Path(temporary)
    for directory in ('src', 'tests', 'models', 'contracts', 'scripts', 'resources', 'config'):
        shutil.copytree(ROOT / directory, clean / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('run', 'pyproject.toml', 'README.md'):
        shutil.copy2(ROOT / name, clean / name)
    if args.candidate_model:
        shutil.copy2(args.candidate_model, clean / 'models/hybrid_ranker.json')
    environment = {'PATH': str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                   'PYTHONPATH': str(clean / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}
    started = time.monotonic()
    process = subprocess.run([sys.executable, 'scripts/run_backend_tests.py', '--out', 'resources/results/clean-tests.json'],
                             cwd=clean, env=environment, text=True, capture_output=True, timeout=120)
    if process.returncode:
        print(process.stderr)
        raise SystemExit(process.returncode)
    tests = json.loads((clean / 'resources/results/clean-tests.json').read_text())
    subprocess.run([sys.executable, str(clean / 'run'), '--data', str(clean / 'resources/examples/sample.xml'),
                    '--queries', str(clean / 'resources/examples/queries.txt'), '--out', str(clean / 'batch.json')],
                   cwd='/tmp', env=environment, check=True, timeout=30)
    payload = json.loads((clean / 'batch.json').read_text())
    if not payload or (clean / 'data').exists():
        raise RuntimeError('Clean batch did not remain isolated from persistent source data')
    unsupported = sum(not claim['supported'] for item in payload for person in item['results'] for claim in person['claims'])
    if unsupported:
        raise RuntimeError('Clean batch emitted unsupported claims')
    command = ['.venv/bin/python', 'scripts/check_clean_copy.py', '--out', str(args.out)]
    if args.candidate_model:
        command.extend(['--candidate-model', str(args.candidate_model)])
    report = {'command': command,
              'tests_run': tests['tests_run'], 'successful': tests['successful'],
              'failures': tests['failures'], 'errors': tests['errors'], 'batch_queries': len(payload),
              'unsupported_batch_claims': unsupported, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'package_source_sha256': tests['package_source_sha256'],
              'scope': 'Clean source/model/recording copy with prepared dependencies; no raw corpus, generated indexes, optional LLM weights or API keys.'}
    write_json(args.out, report)
    print(json.dumps(report, indent=2))
