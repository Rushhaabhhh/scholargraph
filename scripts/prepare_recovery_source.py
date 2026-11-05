#!/usr/bin/env python3
"""Scan the checked archive using a declared cross-CS portfolio; preserve baseline."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, write_json
from hiresense.data.history import enrich_history

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
# Bind the actual selection dependencies separately from unrelated concurrent edits.
root = Path(__file__).resolve().parents[1]
modules = ['scripts/prepare_recovery_source.py', 'src/hiresense/data/history.py',
           'src/hiresense/data/dblp.py', 'src/hiresense/data/xml_stream.py',
           'src/hiresense/data/artifacts.py', 'src/hiresense/models.py']
before = {p: digest_file(root / p) for p in modules}
report = enrich_history(args.config, args.out)
after = {p: digest_file(root / p) for p in modules}
if before != after:
    raise RuntimeError('Selection dependencies changed during archive scan; do not use output')
report.update(selection_dependencies_sha256=before,
              selection_dependencies_unchanged=True,
              limitation='Declared cross-CS venue portfolio plus prior source; not representative random DBLP. '
                         'Future records are labels only and never enter earlier feature snapshots.')
write_json(args.out.with_suffix(args.out.suffix + '.manifest.json'), report)
print(json.dumps({k:report[k] for k in ('total_papers','added_historical_papers','records_scanned','elapsed_seconds')},indent=2))
