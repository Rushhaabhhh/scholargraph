#!/usr/bin/env python3
"""Explicit opt-in download for reproducing local LLM recordings."""
import argparse
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file

parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, default=ROOT / 'data/models/query-understanding.gguf')
args = parser.parse_args()
metadata = json.loads((ROOT / 'recordings/local-model.json').read_text())
if args.out.exists():
    if digest_file(args.out) != metadata['sha256']:
        raise SystemExit('Existing model checksum differs; choose a new output path')
else:
    args.out.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=args.out.parent, prefix='.query-model-')
    try:
        with os.fdopen(descriptor, 'wb') as target, urllib.request.urlopen(metadata['url'], timeout=120) as source:
            while chunk := source.read(1024 * 1024):
                target.write(chunk)
        if digest_file(temporary) != metadata['sha256']:
            raise SystemExit('Downloaded model checksum mismatch')
        os.replace(temporary, args.out)
    finally:
        Path(temporary).unlink(missing_ok=True)
print(args.out)
