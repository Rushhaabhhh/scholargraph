#!/usr/bin/env python3
"""Exercise a candidate on an isolated, different-field XML input offline."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--model', required=True, type=Path)
parser.add_argument('--data', required=True, type=Path)
parser.add_argument('--queries', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
args = parser.parse_args()
if args.out.exists():
    parser.error('Use a new report path')
started = monotonic()
with tempfile.TemporaryDirectory(prefix='hiresense-unseen-clean-') as tmp:
    clean = Path(tmp)
    for directory in ('src', 'scripts', 'models', 'recordings'):
        shutil.copytree(ROOT / directory, clean / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'run', clean / 'run')
    shutil.copy2(args.model, clean / 'models/hybrid_ranker.json')
    environment = {'PATH': str(Path(sys.executable).parent) + os.pathsep + os.defpath,
                   'PYTHONDONTWRITEBYTECODE': '1'}
    output = clean / 'batch.json'
    subprocess.run([sys.executable, str(clean / 'run'), '--data', str(args.data.resolve()),
                    '--queries', str(args.queries.resolve()), '--out', str(output)],
                   cwd='/tmp', env=environment, check=True, timeout=120)
    payload = json.loads(output.read_text())
    if not payload or any(item.get('error') or not item['results'] for item in payload):
        raise RuntimeError('A different-field query failed or returned no candidates')
    unsupported = sum(not claim['supported'] for item in payload for person in item['results'] for claim in person['claims'])
    if unsupported:
        raise RuntimeError('An emitted claim failed grounding')
    report = {'scope': 'Different-field, disjoint XML functional acceptance; not an expert-ranking accuracy test.',
              'data_sha256': digest_file(args.data), 'queries_sha256': digest_file(args.queries),
              'model_sha256': digest_file(args.model), 'package_source_sha256': package_digest(),
              'query_count': len(payload), 'result_counts': [len(item['results']) for item in payload],
              'unsupported_claims': unsupported, 'elapsed_seconds': round(monotonic() - started, 3),
              'command': sys.argv, 'environment': 'Clean code/model copy with prepared dependencies; no API keys.'}
    write_json(args.out, report)
    print(json.dumps(report, indent=2))
