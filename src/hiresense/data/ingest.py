"""Atomic, idempotent ingestion with stable DBLP identities and provenance."""

import hashlib
import json
import resource
import sqlite3
import sys
import tracemalloc
from dataclasses import asdict
from pathlib import Path
from time import monotonic

from .artifacts import digest_file, title_key
from .dblp import iter_publications


def stable_id(source_key: str) -> int:
    # 52 bits fit JavaScript's exact integer range and SQLite and remain deterministic across slices.
    return int(hashlib.sha256(source_key.encode('utf-8')).hexdigest()[:13], 16)


def _author_id(database, name: str, pid: str | None) -> int:
    key = f'dblp:pid:{pid}' if pid else f'dblp:name:{name}'
    identifier = stable_id(key)
    database.execute(
        'INSERT INTO authors(id,source_key,canonical_name) VALUES(?,?,?) '
        'ON CONFLICT(source_key) DO UPDATE SET canonical_name=excluded.canonical_name',
        (identifier, key, name),
    )
    # A hash collision raises a primary-key error rather than silently merging people.
    return identifier


def ingest(database: sqlite3.Connection, source_path: str | Path) -> dict:
    started = monotonic()
    source_hash = digest_file(source_path)
    if database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone():
        raise ValueError('Graph snapshots are immutable; ingest into a source database')
    run_id = database.execute(
        "INSERT INTO ingestion_runs(source_path,source_sha256,status) VALUES(?,?,'running')",
        (str(source_path), source_hash),
    ).lastrowid
    database.commit()
    parse_stats = {}
    seen = inserted = updated = unchanged = 0
    owns_trace = not tracemalloc.is_tracing()
    if owns_trace:
        tracemalloc.start()
    try:
        database.execute('BEGIN IMMEDIATE')
        for publication in iter_publications(source_path, parse_stats):
            seen += 1
            content_hash = hashlib.sha256(json.dumps(asdict(publication), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            old = database.execute('SELECT content_sha256 FROM papers WHERE id=?', (publication.key,)).fetchone()
            if old and old[0] == content_hash:
                unchanged += 1
                continue
            inserted += old is None
            updated += old is not None
            database.execute(
                '''INSERT INTO papers(id,title,title_key,year,venue,record_type,content_sha256)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title,title_key=excluded.title_key,year=excluded.year,
                   venue=excluded.venue,record_type=excluded.record_type,content_sha256=excluded.content_sha256''',
                (publication.key, publication.title, title_key(publication.title), publication.year,
                 publication.venue, publication.record_type, content_hash),
            )
            database.execute('DELETE FROM paper_authors WHERE paper_id=?', (publication.key,))
            database.execute('DELETE FROM paper_venues WHERE paper_id=?', (publication.key,))
            database.execute('DELETE FROM context_edges WHERE source_record_id=?', (publication.key,))
            seen_authors = set()
            for position, name in enumerate(publication.authors):
                pid = publication.author_pids[position] if publication.author_pids else None
                author_id = _author_id(database, name, pid)
                if author_id in seen_authors:
                    continue
                seen_authors.add(author_id)
                database.execute('INSERT INTO paper_authors VALUES(?,?,?,?)', (publication.key, author_id, position, name))
            if publication.venue:
                database.execute('INSERT OR IGNORE INTO venues(name) VALUES(?)', (publication.venue,))
                database.execute(
                    'INSERT INTO paper_venues SELECT ?,id FROM venues WHERE name=?',
                    (publication.key, publication.venue),
                )
        # Remove identities/venues that no longer have evidence after source corrections.
        if inserted or updated:
            database.execute('DELETE FROM entity_resolution_matches')
            database.execute('DELETE FROM entity_resolution_candidates')
        database.execute('DELETE FROM authors WHERE NOT EXISTS (SELECT 1 FROM paper_authors pa WHERE pa.author_id=authors.id)')
        database.execute('DELETE FROM venues WHERE NOT EXISTS (SELECT 1 FROM paper_venues pv WHERE pv.venue_id=venues.id)')
        database.execute(
            "UPDATE ingestion_runs SET completed_at=CURRENT_TIMESTAMP,records_seen=?,records_loaded=?,status='completed' WHERE id=?",
            (seen, seen, run_id),
        )
        database.commit()
    except BaseException as error:
        database.rollback()
        database.execute(
            "UPDATE ingestion_runs SET completed_at=CURRENT_TIMESTAMP,records_seen=?,status='failed',error=? WHERE id=?",
            (seen, str(error), run_id),
        )
        database.commit()
        raise
    finally:
        _, peak_memory = tracemalloc.get_traced_memory()
        if owns_trace:
            tracemalloc.stop()
    elapsed = monotonic() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        'source_sha256': source_hash, 'records_seen': seen, 'records_loaded': seen, 'parser': parse_stats,
        'inserted': inserted, 'updated': updated, 'unchanged': unchanged, 'run_id': run_id,
        'elapsed_seconds': round(elapsed, 3), 'records_per_second': round(seen / max(elapsed, 1e-9), 2),
        'peak_python_memory_mb': round(peak_memory / 1048576, 2),
        'process_peak_rss_mb': round(rss / (1048576 if sys.platform == 'darwin' else 1024), 2),
        'memory_measurement': 'tracemalloc peak during ingest; process lifetime RSS high-water mark',
    }
