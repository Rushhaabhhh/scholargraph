"""Materialize retrieval features without injecting any ground-truth candidates."""

import json
import sys
from pathlib import Path
from time import monotonic

import numpy as np

from ..data.artifacts import digest_file, write_json
from ..retrieval.index import FEATURE_NAMES
from ..graph.build import graph_digest
from .split import assert_no_leakage, load_queries


def load_partition(dataset: str | Path, role: str, database):
    if role not in ('train', 'validation', 'test'):
        raise ValueError('Unknown temporal partition')
    directory = Path(dataset)
    manifest = json.loads((directory / 'manifest.json').read_text())
    file = directory / f'{role}_ground_truth.jsonl'
    if digest_file(file) != manifest['files'][file.name]:
        raise ValueError('Ground truth file differs from the prepared dataset manifest')
    source = database.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
    if source is None or source[0] != manifest['source_dataset_sha256']:
        raise ValueError('Graph and label dataset provenance differ')
    queries = load_queries(file)
    boundaries = manifest['split']
    lower, upper = {'train': (boundaries['graph_cutoff_year'], boundaries['train_end_year']),
                    'validation': (boundaries['train_end_year'], boundaries['validation_end_year']),
                    'test': (boundaries['validation_end_year'], boundaries['test_end_year'])}[role]
    if any(not lower < query.year <= upper for query in queries):
        raise ValueError('Ground truth years violate their declared partition')
    assert_no_leakage(database, queries, [], boundaries['graph_cutoff_year'])
    return queries, digest_file(file)


def materialize(engine, queries, directory: str | Path, labels_sha256: str):
    directory = Path(directory)
    signature = {'content_sha256': engine.manifest['content_sha256'], 'encoder_sha256': engine.encoder.signature,
                 'graph_sha256': graph_digest(engine.database), 'feature_version': 1, 'labels_sha256': labels_sha256, 'features': list(FEATURE_NAMES),
                 'paper_limit': engine.paper_limit, 'candidate_limit': engine.candidate_limit}
    data_file, manifest_file = directory / 'features.npz', directory / 'manifest.json'
    if directory.exists():
        manifest = json.loads(manifest_file.read_text())
        if manifest['signature'] != signature or manifest['features_sha256'] != digest_file(data_file):
            raise ValueError('Stale or corrupted retrieval feature cache')
        with np.load(data_file, allow_pickle=False) as stored:
            cache = {name: stored[name] for name in stored.files}
        cache['queries'] = queries
        return cache
    directory.mkdir(parents=True)
    started = monotonic()
    features, author_ids, offsets, lexical, dense = [], [], [0], [], []
    for index, query in enumerate(queries):
        retrieved = engine.retrieve(query.text)
        features.append(retrieved['features'])
        author_ids.extend(retrieved['author_ids'])
        offsets.append(len(author_ids))
        lexical.append((retrieved['lexical'] + [-1] * engine.candidate_limit)[:engine.candidate_limit])
        dense.append((retrieved['dense'] + [-1] * engine.candidate_limit)[:engine.candidate_limit])
        if (index + 1) % 500 == 0:
            print(f'Materialized {index + 1}/{len(queries)} queries in {monotonic() - started:.1f}s', flush=True, file=sys.stderr)
    cache = {'features': np.concatenate(features) if features else np.empty((0, len(FEATURE_NAMES)), dtype=np.float32),
             'author_ids': np.asarray(author_ids, dtype=np.int64), 'offsets': np.asarray(offsets, dtype=np.int64),
             'lexical': np.asarray(lexical, dtype=np.int64), 'dense': np.asarray(dense, dtype=np.int64)}
    np.savez_compressed(data_file, **cache)
    write_json(manifest_file, {'signature': signature, 'features_sha256': digest_file(data_file),
                               'queries': len(queries), 'candidate_rows': len(author_ids),
                               'elapsed_seconds': round(monotonic() - started, 3)})
    cache['queries'] = queries
    return cache
