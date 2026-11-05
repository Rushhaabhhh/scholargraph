#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.db import connect
from hiresense.evaluation.transfer import transfer_cohort

parser = argparse.ArgumentParser(description='Transfer fixed pilot labels onto enriched historical evidence')
for name in ('parent', 'dataset', 'graph', 'out'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--train-queries', type=int, default=3000)
args = parser.parse_args()
if not args.graph.is_file():
    parser.error('Graph must already exist')
graph = connect(args.graph)
try:
    print(json.dumps(transfer_cohort(args.parent, args.dataset, graph, args.out, args.train_queries), indent=2))
finally:
    graph.close()
