"""SQLite system of record; graph snapshots use the identical schema."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    error TEXT
);
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    title_key TEXT NOT NULL DEFAULT '',
    year INTEGER CHECK(year IS NULL OR year BETWEEN 1 AND 9999),
    venue TEXT,
    record_type TEXT NOT NULL DEFAULT 'article',
    source TEXT NOT NULL DEFAULT 'dblp',
    content_sha256 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'dblp'
);
CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    author_position INTEGER NOT NULL,
    observed_name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (paper_id, author_id),
    UNIQUE (paper_id, author_position)
);
CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS paper_venues (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    venue_id INTEGER NOT NULL REFERENCES venues(id),
    PRIMARY KEY (paper_id, venue_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_venues_venue ON paper_venues(venue_id, paper_id);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title_key);
CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(canonical_name);
CREATE INDEX IF NOT EXISTS idx_paper_authors_author ON paper_authors(author_id, paper_id);
CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
    noisy_record_id TEXT PRIMARY KEY,
    candidate_ids_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_resolution_matches (
    noisy_record_id TEXT PRIMARY KEY,
    canonical_author_id INTEGER REFERENCES authors(id),
    score REAL NOT NULL,
    decision TEXT NOT NULL,
    features_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS context_edges (
    edge_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    edge_year INTEGER,
    source_record_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    UNIQUE(source_id, target_id, edge_type, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_context_edges_source ON context_edges(source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_context_edges_target ON context_edges(target_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_context_edges_record ON context_edges(source_record_id);
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    database.execute("PRAGMA journal_mode = WAL")
    database.execute("PRAGMA busy_timeout = 5000")
    return database


def initialize(database: sqlite3.Connection) -> None:
    version = database.execute("PRAGMA user_version").fetchone()[0]
    existing = database.execute("SELECT 1 FROM sqlite_master WHERE name='papers'").fetchone()
    if existing and version != SCHEMA_VERSION:
        raise ValueError("Legacy database schema; ingest the source into a new database path")
    if version not in (0, SCHEMA_VERSION):
        raise ValueError(f"Unsupported database schema version: {version}")
    database.executescript(SCHEMA)
    database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    database.commit()
