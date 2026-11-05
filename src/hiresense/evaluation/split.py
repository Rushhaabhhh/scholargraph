"""A frozen history graph and three disjoint, strictly later label periods.

Training labels predict future paper authors from older history. Validation selects
settings; the test labels stay untouched until final evaluation. Every split uses
the same history graph to make feature availability explicit and reproducible.
"""

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..contracts import CONTRACT_VERSION, SplitConfig
from ..data.artifacts import digest_file, title_key, write_json
from ..db import connect, initialize
from ..models import GroundTruthQuery


def dataset_digest(database) -> str:
    digest = hashlib.sha256()
    for row in database.execute('SELECT id,content_sha256 FROM papers ORDER BY id'):
        digest.update(json.dumps(list(row), ensure_ascii=False).encode() + b'\n')
    return digest.hexdigest()


def export_snapshot(source, target_path: Path, cutoff: int, source_digest: str) -> dict:
    target = connect(target_path)
    try:
        initialize(target)
        with target:
            target.executemany(
                'INSERT INTO papers VALUES(?,?,?,?,?,?,?,?)',
                (tuple(row) for row in source.execute('SELECT * FROM papers WHERE year <= ? ORDER BY id', (cutoff,))),
            )
            # Choose a historical observed label, rather than a later PID rename.
            target.executemany(
                'INSERT INTO authors(id,source_key,canonical_name,source) VALUES(?,?,?,?)',
                (tuple(row) for row in source.execute('''
                    SELECT a.id,a.source_key,
                    (SELECT pa.observed_name FROM paper_authors pa JOIN papers p ON p.id=pa.paper_id
                     WHERE pa.author_id=a.id AND p.year <= ? ORDER BY p.year,p.id LIMIT 1),a.source
                    FROM authors a WHERE EXISTS (
                        SELECT 1 FROM paper_authors pa JOIN papers p ON p.id=pa.paper_id
                        WHERE pa.author_id=a.id AND p.year <= ?) ORDER BY a.id''', (cutoff, cutoff))),
            )
            target.executemany(
                'INSERT INTO paper_authors VALUES(?,?,?,?)',
                (tuple(row) for row in source.execute('''SELECT pa.* FROM paper_authors pa
                    JOIN papers p ON p.id=pa.paper_id WHERE p.year <= ? ORDER BY pa.paper_id,pa.author_position''', (cutoff,))),
            )
            target.executemany(
                'INSERT INTO venues VALUES(?,?)',
                (tuple(row) for row in source.execute('''SELECT v.* FROM venues v WHERE EXISTS (
                    SELECT 1 FROM paper_venues pv JOIN papers p ON p.id=pv.paper_id
                    WHERE pv.venue_id=v.id AND p.year <= ?) ORDER BY v.id''', (cutoff,))),
            )
            target.executemany(
                'INSERT INTO paper_venues VALUES(?,?)',
                (tuple(row) for row in source.execute('''SELECT pv.* FROM paper_venues pv
                    JOIN papers p ON p.id=pv.paper_id WHERE p.year <= ? ORDER BY pv.paper_id''', (cutoff,))),
            )
            target.executemany('INSERT INTO metadata VALUES(?,?)', [
                ('graph_cutoff_year', str(cutoff)), ('source_dataset_sha256', source_digest),
                ('contract_version', str(CONTRACT_VERSION)),
            ])
        assert_no_leakage(target, [], [], cutoff)
        counts = {table: target.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('papers', 'authors', 'venues', 'paper_authors')}
        target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return counts
    finally:
        target.close()


def load_queries(path: str | Path) -> list[GroundTruthQuery]:
    output = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            payload = json.loads(line)
            payload['relevant_author_ids'] = tuple(payload['relevant_author_ids'])
            query = GroundTruthQuery(**payload)
            if not query.text or not query.relevant_author_ids or not 1 <= query.year <= 9999:
                raise ValueError('Invalid ground truth query')
            output.append(query)
    return output


def write_split(database, output_dir: str | Path, config: SplitConfig) -> dict:
    directory = Path(output_dir)
    if directory.exists():
        raise ValueError('Dataset output must be a new directory; existing experiments are never overwritten')
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(dir=directory.parent, prefix='.dataset-'))
    source_digest = dataset_digest(database)
    try:
        counts = export_snapshot(database, temporary / 'graph.sqlite3', config.graph_cutoff_year, source_digest)
        if counts['papers'] == 0:
            raise ValueError('Graph period is empty; choose a cutoff supported by this dataset')
        known_authors = {row[0] for row in database.execute('''SELECT DISTINCT pa.author_id FROM paper_authors pa
            JOIN papers p ON p.id=pa.paper_id WHERE p.year <= ?''', (config.graph_cutoff_year,))}
        # A repeated title can reveal the held-out answer even when paper keys differ.
        duplicate_titles = {row[0] for row in database.execute(
            'SELECT title_key FROM papers GROUP BY title_key HAVING COUNT(*) > 1')}
        split_stats = {}
        previous = config.graph_cutoff_year
        for split, end in (('train', config.train_end_year), ('validation', config.validation_end_year), ('test', config.test_end_year)):
            stats = {'queries': 0, 'duplicate_titles_excluded': 0, 'authorless_excluded': 0,
                     'relevant_authors': 0, 'retrievable_relevant_authors': 0, 'queries_with_history': 0}
            with (temporary / f'{split}_ground_truth.jsonl').open('w', encoding='utf-8') as stream:
                for paper in database.execute('SELECT id,title,title_key,year FROM papers WHERE year > ? AND year <= ? ORDER BY id', (previous, end)):
                    if paper['title_key'] in duplicate_titles:
                        stats['duplicate_titles_excluded'] += 1
                        continue
                    authors = tuple(row[0] for row in database.execute(
                        'SELECT author_id FROM paper_authors WHERE paper_id=? ORDER BY author_position', (paper['id'],)))
                    if not authors:
                        stats['authorless_excluded'] += 1
                        continue
                    query = GroundTruthQuery(f"paper:{paper['id']}", paper['title'], paper['id'], paper['year'], authors)
                    stream.write(json.dumps(asdict(query), ensure_ascii=False, sort_keys=True) + '\n')
                    covered = len(set(authors) & known_authors)
                    stats['queries'] += 1
                    stats['relevant_authors'] += len(authors)
                    stats['retrievable_relevant_authors'] += covered
                    stats['queries_with_history'] += covered > 0
            if stats['queries'] == 0:
                raise ValueError(f'{split} period has no usable queries; choose different years or a broader slice')
            stats['author_history_coverage'] = stats['retrievable_relevant_authors'] / stats['relevant_authors']
            stats['query_history_coverage'] = stats['queries_with_history'] / stats['queries']
            split_stats[split] = stats
            previous = end
        graph = connect(temporary / 'graph.sqlite3')
        try:
            all_queries = [load_queries(temporary / f'{split}_ground_truth.jsonl') for split in split_stats]
            assert_no_leakage(graph, all_queries[0], all_queries[1] + all_queries[2], config.graph_cutoff_year)
        finally:
            graph.close()
        manifest = {
            'contract_version': CONTRACT_VERSION, 'source_dataset_sha256': source_digest,
            'split': asdict(config), 'graph': counts, 'labels': split_stats,
            'unknown_year_papers_excluded': database.execute('SELECT COUNT(*) FROM papers WHERE year IS NULL').fetchone()[0],
            'papers_after_test_end_excluded': database.execute('SELECT COUNT(*) FROM papers WHERE year > ?', (config.test_end_year,)).fetchone()[0],
            'protocol': 'Frozen history graph; subsequent disjoint train, validation and test label periods.',
            'label_limitations': 'Future publication authorship is a proxy for expertise. Missing history limits achievable recall; non-authors are unjudged, not proven irrelevant.',
            'files': {path.name: digest_file(path) for path in sorted(temporary.iterdir()) if path.is_file()},
        }
        write_json(temporary / 'manifest.json', manifest)
        temporary.rename(directory)
        return manifest
    except BaseException:
        shutil.rmtree(temporary)
        raise


def assert_no_leakage(database, training_queries: list[GroundTruthQuery], evaluation_queries: list[GroundTruthQuery], cutoff_year: int) -> None:
    if database.execute('SELECT COUNT(*) FROM papers WHERE year IS NULL OR year > ?', (cutoff_year,)).fetchone()[0]:
        raise ValueError('Graph database contains unknown-year or post-cutoff papers')
    if database.execute('SELECT COUNT(*) FROM context_edges WHERE edge_year IS NULL OR edge_year > ?', (cutoff_year,)).fetchone()[0]:
        raise ValueError('Graph database contains unknown-year or post-cutoff edges')
    query_ids, source_ids, titles = set(), set(), set()
    for query in [*training_queries, *evaluation_queries]:
        normalized = title_key(query.text)
        if query.year <= cutoff_year or query.query_id in query_ids or query.source_paper_id in source_ids or normalized in titles:
            raise ValueError('Overlapping or non-future ground truth queries')
        if database.execute('SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1', (query.source_paper_id, normalized)).fetchone():
            raise ValueError('Ground truth source paper or title appears in graph history')
        query_ids.add(query.query_id)
        source_ids.add(query.source_paper_id)
        titles.add(normalized)
