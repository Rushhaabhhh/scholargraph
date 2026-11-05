"""Atomic graph reconstruction with typed, dated, per-paper provenance."""

import hashlib
import json
import sqlite3
from time import monotonic


def graph_digest(database):
    digest = hashlib.sha256()
    for row in database.execute('SELECT * FROM context_edges ORDER BY edge_id'):
        digest.update(json.dumps(list(row), ensure_ascii=False).encode() + b'\n')
    return digest.hexdigest()



def validate_graph(database):
    invalid = database.execute("""SELECT COUNT(*) FROM context_edges e LEFT JOIN papers p ON p.id=e.source_record_id
        WHERE p.id IS NULL OR e.edge_year IS NULL OR e.edge_year IS NOT p.year
        OR e.edge_type NOT IN ('author_paper','author_venue','coauthorship')""").fetchone()[0]
    tests = {
        'author_paper': """SELECT 1 FROM paper_authors pa WHERE pa.paper_id=e.source_record_id
            AND e.source_id='author:'||pa.author_id AND e.target_id='paper:'||pa.paper_id""",
        'author_venue': """SELECT 1 FROM paper_authors pa JOIN paper_venues pv ON pv.paper_id=pa.paper_id
            WHERE pa.paper_id=e.source_record_id AND e.source_id='author:'||pa.author_id AND e.target_id='venue:'||pv.venue_id""",
        'coauthorship': """SELECT 1 FROM paper_authors a JOIN paper_authors b ON b.paper_id=a.paper_id
            WHERE a.paper_id=e.source_record_id AND a.author_id<b.author_id
            AND e.source_id='author:'||a.author_id AND e.target_id='author:'||b.author_id""",
    }
    for kind, predicate in tests.items():
        invalid += database.execute(f'SELECT COUNT(*) FROM context_edges e WHERE e.edge_type=? AND NOT EXISTS ({predicate})', (kind,)).fetchone()[0]
    if invalid:
        raise ValueError(f'Graph contains {invalid} unsupported, mistyped, or incorrectly dated edges')
    if database.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Broken graph foreign keys')
    return {'unsupported_edges': 0, 'foreign_keys_valid': True}

def build_context_graph(database: sqlite3.Connection, cutoff_year: int | None = None) -> dict:
    started = monotonic()
    snapshot = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if snapshot:
        if cutoff_year is not None and cutoff_year != int(snapshot[0]):
            raise ValueError('Graph cutoff must match the prepared snapshot')
        cutoff_year = int(snapshot[0])
    if cutoff_year is None:
        raise ValueError('A graph cutoff year is required')
    with database:
        # Rebuild, rather than append, so corrections and stricter cutoffs cannot leave stale edges.
        database.execute('DELETE FROM context_edges')
        database.execute('''INSERT INTO context_edges
            SELECT 'author_paper:author:'||pa.author_id||':paper:'||p.id,
                   'author:'||pa.author_id,'paper:'||p.id,'author_paper',p.year,p.id,1.0
            FROM paper_authors pa JOIN papers p ON p.id=pa.paper_id WHERE p.year<=?''', (cutoff_year,))
        database.execute('''INSERT INTO context_edges
            SELECT 'author_venue:author:'||pa.author_id||':venue:'||pv.venue_id||':'||p.id,
                   'author:'||pa.author_id,'venue:'||pv.venue_id,'author_venue',p.year,p.id,1.0
            FROM paper_authors pa JOIN papers p ON p.id=pa.paper_id JOIN paper_venues pv ON pv.paper_id=p.id
            WHERE p.year<=?''', (cutoff_year,))
        database.execute('''INSERT INTO context_edges
            SELECT 'coauthorship:author:'||a.author_id||':author:'||b.author_id||':'||p.id,
                   'author:'||a.author_id,'author:'||b.author_id,'coauthorship',p.year,p.id,1.0
            FROM paper_authors a JOIN paper_authors b ON b.paper_id=a.paper_id AND a.author_id<b.author_id
            JOIN papers p ON p.id=a.paper_id WHERE p.year<=?''', (cutoff_year,))
        integrity = validate_graph(database)
        digest = graph_digest(database)
        database.execute("INSERT OR REPLACE INTO metadata VALUES('graph_content_sha256',?)", (digest,))
    counts = {row[0]: row[1] for row in database.execute('SELECT edge_type,COUNT(*) FROM context_edges GROUP BY edge_type')}
    return {**counts, 'coauthorship_edges': counts.get('coauthorship', 0), 'context_edges': sum(counts.values()),
            'papers_scanned': database.execute('SELECT COUNT(*) FROM papers WHERE year<=?', (cutoff_year,)).fetchone()[0],
            'sha256': digest, 'integrity': integrity, 'elapsed_seconds': round(monotonic() - started, 3)}
