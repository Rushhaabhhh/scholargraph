#!/usr/bin/env python3
"""Package a prepared local graph and index for the backend Docker image."""

import argparse
import io
import json
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Local backend.json to package')
    parser.add_argument('--out', type=Path, required=True, help='New uncompressed tar archive')
    args = parser.parse_args()
    config_path = args.config.resolve(strict=True)
    config = json.loads(config_path.read_text())
    graph = (config_path.parent / config['graph']).resolve(strict=True)
    index = (config_path.parent / config['index']).resolve(strict=True)
    if not graph.is_file() or not (index / 'manifest.json').is_file():
        parser.error('Configuration must point to a graph file and a prepared index')
    if args.out.resolve().is_relative_to(index) or args.out.resolve() == graph:
        parser.error('Archive must be outside the graph and index')
    # Models and recordings are already included in the Docker image. Sessions
    # are intentionally excluded and created separately on the deployment disk.
    deployed = {
        'graph': 'graph.sqlite3', 'index': 'index', 'session_db': 'sessions.sqlite3',
        'encoder': '/app/models/minilm', 'model': '/app/models/hybrid_ranker.json',
        'cross_encoder': '/app/models/crossencoder',
        'recordings': '/app/resources/recordings/query-intents.json',
        'query_provider': 'recorded',
    }
    model = json.loads((config_path.parent / config['model']).read_text())
    image_model = json.loads((Path(__file__).resolve().parents[1] / 'models/hybrid_ranker.json').read_text())
    if model != image_model:
        parser.error('The configured ranker differs from models/hybrid_ranker.json in the Docker image')
    payload = (json.dumps(deployed, indent=2) + '\n').encode()
    with args.out.open('xb') as output, tarfile.open(fileobj=output, mode='w') as archive:
        entry = tarfile.TarInfo('backend.json')
        entry.size = len(payload)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(payload))
        archive.add(graph, arcname='graph.sqlite3')
        archive.add(index, arcname='index')
    print(f'Created {args.out}. Extract into an empty deployment directory.')


if __name__ == '__main__':
    main()
