"""Reproduce and measure the complete offline data preparation experiment."""

import hashlib
import json
import platform
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from time import monotonic

from ..contracts import CONTRACT_VERSION, SplitConfig
from ..db import connect, initialize
from ..evaluation.split import assert_no_leakage, load_queries, write_split
from .artifacts import digest_file, package_digest, write_json
from .ingest import ingest
from .noise import generate_noisy_authors
from .slice import create_slice


def _database_state(database) -> dict:
    state = {}
    for table in ('papers', 'authors', 'venues', 'paper_authors', 'paper_venues', 'context_edges'):
        digest, count = hashlib.sha256(), 0
        for row in database.execute(f'SELECT * FROM {table} ORDER BY 1,2'):
            digest.update(json.dumps(list(row), ensure_ascii=False).encode() + b'\n')
            count += 1
        state[table] = {'rows': count, 'sha256': digest.hexdigest()}
    return state



def run_experiment(config_path: str | Path, output_dir: str | Path, report_path: str | Path) -> dict:
    config_path, output_dir, report_path = Path(config_path), Path(output_dir), Path(report_path)
    config = json.loads(config_path.read_text(encoding='utf-8'))
    if config.get('contract_version') != CONTRACT_VERSION:
        raise ValueError('Unsupported experiment contract version')
    split_config = SplitConfig(**config['split'])
    if config['slice']['limit'] < 50000:
        raise ValueError('The measured acceptance experiment must contain at least 50000 papers')
    if report_path.resolve().is_relative_to(output_dir.resolve()):
        raise ValueError('Results report must be outside the experiment artifact directory')
    if not config.get('checksum'):
        raise ValueError('The acceptance experiment requires a supplied DBLP checksum')
    if output_dir.exists() or report_path.exists():
        raise ValueError('Experiment output and results report must be new paths')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output_dir.parent, prefix='.experiment-'))
    started = monotonic()
    try:
        selection = config['slice']
        slice_report = create_slice(
            config['source'], stage / 'source.xml', selection['limit'],
            selection['min_year'], selection['max_year'], tuple(selection['record_types']), config.get('checksum'),
        )
        print(f"Prepared {slice_report['papers']} papers; source checksum verified.", file=sys.stderr, flush=True)
        database = connect(stage / 'source.sqlite3')
        try:
            initialize(database)
            first = ingest(database, stage / 'source.xml')
            before = _database_state(database)
            repeated = ingest(database, stage / 'source.xml')
            after = _database_state(database)
            if before != after or repeated['inserted'] or repeated['updated']:
                raise ValueError('Repeated ingestion changed graph records')
            print('Ingestion and repeated-ingestion checks passed.', file=sys.stderr, flush=True)
            split_started = monotonic()
            dataset = write_split(database, stage / 'dataset', split_config)
            split_seconds = monotonic() - split_started
            with tempfile.TemporaryDirectory(prefix='hiresense-reproduce-') as tmp:
                other = write_split(database, Path(tmp) / 'dataset', split_config)
                if dataset != other:
                    raise ValueError('Dataset snapshot and labels failed reproduction')
        finally:
            database.close()
        graph = connect(stage / 'dataset/graph.sqlite3')
        try:
            queries = [load_queries(stage / 'dataset' / f'{name}_ground_truth.jsonl') for name in ('train', 'validation', 'test')]
            assert_no_leakage(graph, queries[0], queries[1] + queries[2], split_config.graph_cutoff_year)
            if graph.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Snapshot contains broken foreign keys')
            noise_started = monotonic()
            noise_file = stage / 'noisy_authors.jsonl'
            noise_count = generate_noisy_authors(graph, noise_file, **config['noise'])
            noise_seconds = monotonic() - noise_started
            with tempfile.TemporaryDirectory(prefix='hiresense-noise-') as tmp:
                other = Path(tmp) / 'noisy_authors.jsonl'
                generate_noisy_authors(graph, other, **config['noise'])
                if (digest_file(noise_file) != digest_file(other)
                        or digest_file(noise_file.with_suffix('.truth.jsonl')) != digest_file(other.with_suffix('.truth.jsonl'))):
                    raise ValueError('Seeded noise failed reproduction')
        finally:
            graph.close()
        print('Temporal isolation, artifact reproduction, and noise checks passed.', file=sys.stderr, flush=True)
        result = {
            'contract_version': CONTRACT_VERSION, 'config': config, 'config_sha256': digest_file(config_path),
            'package_source_sha256': package_digest(),
            'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                            'platform': platform.platform(), 'machine': platform.machine()},
            'command': ['python3', '-m', 'hiresense.cli', 'benchmark', '--config', str(config_path),
                        '--out', str(output_dir), '--report', str(report_path)],
            'environment_variables': {'PYTHONPATH': 'src'},
            'source': slice_report, 'initial_ingestion': first, 'repeated_ingestion': repeated,
            'table_state': after, 'dataset': dataset, 'noisy_observations': noise_count,
            'preparation_seconds': {'split': round(split_seconds, 3), 'noise': round(noise_seconds, 3)},
            'checks': {'ingestion_idempotent': True, 'foreign_keys_valid': True,
                       'no_future_or_unknown_year_graph_papers': True,
                       'no_label_papers_or_repeated_titles_in_graph': True,
                       'disjoint_train_validation_test_periods': True,
                       'dataset_reproduced': True, 'noise_reproduced': True},
            'elapsed_seconds': round(monotonic() - started, 3),
            'artifact_directory': str(output_dir),
        }
        # Audit records should refer to the final artifact, not its staging path.
        source_db = connect(stage / 'source.sqlite3')
        try:
            source_db.execute('UPDATE ingestion_runs SET source_path=?', (str(output_dir / 'source.xml'),))
            source_db.commit()
        finally:
            source_db.close()
        stage.rename(output_dir)
        write_json(report_path, result)
        return result
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
