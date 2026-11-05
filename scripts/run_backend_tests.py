#!/usr/bin/env python3
"""Run all offline regressions and save a small machine-readable test report."""

import argparse
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
if args.out.exists():
    raise SystemExit('Use a new test-report path')
started = time.monotonic()
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
report = {'command': ['.venv/bin/python', 'scripts/run_backend_tests.py', '--out', str(args.out)],
          'environment_variables': {'PYTHONPATH': 'src', 'PYTHONDONTWRITEBYTECODE': '1'},
          'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
          'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
          'elapsed_seconds': round(time.monotonic() - started, 3),
          'package_source_sha256': package_digest(), 'batch_entrypoint_sha256': digest_file(ROOT / 'run'),
          'failure_tests': [test.id() for test, _ in result.failures], 'error_tests': [test.id() for test, _ in result.errors],
          'scope': 'Data, graph, ML, schemas, HTTP, assistant, grounding, privacy, retries and concurrency; prepared dependencies/models, no API keys or external services.'}
write_json(args.out, report)
print(json.dumps(report, indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
