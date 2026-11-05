#!/usr/bin/env python3
"""Prepare a deliberate historical DBLP slice by scanning the entire archive."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.history import enrich_history

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
print(json.dumps(enrich_history(args.config, args.out), indent=2))
