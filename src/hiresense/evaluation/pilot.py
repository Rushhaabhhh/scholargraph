"""Create deterministic pilot labels and a reserved later cohort without training."""

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..data.artifacts import digest_file, package_digest, title_key, write_json
from .features import load_partition
from .split import assert_no_leakage, dataset_digest


def _sample(queries, count, seed, role):
    if count < 1 or len(queries) < count:
        raise ValueError(f'Not enough {role} queries for requested sample size')
    def priority(query):
        raw = f'{seed}:{role}:{query.query_id}'.encode('utf-8')
        return hashlib.sha256(raw).digest(), query.query_id
    return sorted(queries, key=priority)[:count]


def create_pilot(dataset, graph, excluded_source, output, *, train_count=1200, validation_count=400,
                 seed=42, test_start=2025):
    """Reserve later records outside the prior source slice; no model evaluation occurs.

    Test labels are copied and checked mechanically. Their individual records are not
    reported or scored. Aggregate counts of the parent dataset were already observed.
    """
    dataset, output = Path(dataset), Path(output)
    if output.exists():
        raise ValueError('Pilot output must be a new path')
    parent = json.loads((dataset / 'manifest.json').read_text())
    cutoff = parent['split']['graph_cutoff_year']
    if not parent['split']['validation_end_year'] < test_start <= parent['split']['test_end_year']:
        raise ValueError('Reserved test start must be after validation and within the parent test period')
    # These source records were included in the earlier 50k baseline experiment.
    excluded_ids, excluded_titles = set(), set()
    for row in excluded_source.execute('SELECT id,title_key FROM papers'):
        excluded_ids.add(row[0])
        excluded_titles.add(row[1])
    if not excluded_ids:
        raise ValueError('Prior source must contain records to exclude')
    partitions = {}
    hashes = {}
    for role in ('train', 'validation', 'test'):
        partitions[role], hashes[role] = load_partition(dataset, role, graph)
    def novel(query):
        return query.source_paper_id not in excluded_ids and title_key(query.text) not in excluded_titles
    train = _sample(partitions['train'], train_count, seed, 'train')
    validation_pool = [query for query in partitions['validation'] if novel(query)]
    validation = _sample(validation_pool, validation_count, seed, 'validation')
    test = [query for query in partitions['test'] if query.year >= test_start and novel(query)]
    if not test:
        raise ValueError('Reserved test cohort is empty')
    # Enforce key/title uniqueness and time boundaries even across newly sampled roles.
    assert_no_leakage(graph, train, validation + test, cutoff)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output.parent, prefix='.pilot-'))
    try:
        files = {}
        for role, queries in (('train', train), ('validation', validation), ('test', test)):
            path = stage / f'{role}_ground_truth.jsonl'
            with path.open('w', encoding='utf-8') as stream:
                for query in queries:
                    stream.write(json.dumps(asdict(query), ensure_ascii=False, sort_keys=True) + '\n')
            files[path.name] = digest_file(path)
        manifest = {'contract_version': parent['contract_version'],
                    'source_dataset_sha256': parent['source_dataset_sha256'], 'split': parent['split'],
                    'package_source_sha256': package_digest(),
                    'files': files, 'protocol': 'Deterministic training pilot, novel validation and reserved later novel test.',
                    'selection': {'seed': seed, 'algorithm': 'sha256 of seed:role:query_id, ascending',
                                  'train_count': len(train), 'validation_count': len(validation),
                                  'validation_pool': len(validation_pool), 'reserved_test_count': len(test),
                                  'reserved_test_start_year': test_start,
                                  'validation_and_test_exclude_prior_source_keys_and_normalized_titles': True,
                                  'excluded_source_records': len(excluded_ids),
                                  'excluded_source_dataset_sha256': dataset_digest(excluded_source),
                                  'parent_manifest_sha256': digest_file(dataset / 'manifest.json'),
                                  'parent_labels_sha256': hashes},
                    'limitation': 'Same source-order DBLP slice; parent test aggregate counts were previously observed. '
                                  'Reserved records have not been scored here; external unseen-slice testing is still required.'}
        write_json(stage / 'manifest.json', manifest)
        stage.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(stage)
        raise
