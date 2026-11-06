"""Persistent session memory with optimistic revisions and idempotent retries."""

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from .errors import BackendError

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sessions(
    id TEXT PRIMARY KEY, dataset_sha256 TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
    last_query TEXT, last_intent_json TEXT, last_results_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS decisions(
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('shortlist','reject')),
    PRIMARY KEY(session_id,person_id)
);
CREATE TABLE IF NOT EXISTS requests(
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, request_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL, response_json TEXT NOT NULL,
    PRIMARY KEY(session_id,request_id)
);
'''


def request_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class SessionStore:
    def __init__(self, path, dataset_sha256):
        self.path, self.dataset_sha256 = Path(path), dataset_sha256
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as database:
            database.executescript(SCHEMA)
        os.chmod(self.path, 0o600)

    def _connect(self):
        database = sqlite3.connect(self.path, timeout=5)
        database.row_factory = sqlite3.Row
        database.execute('PRAGMA foreign_keys=ON')
        return database

    def create(self):
        session_id = uuid.uuid4().hex
        with closing(self._connect()) as database, database:
            database.execute('INSERT INTO sessions(id,dataset_sha256) VALUES(?,?)', (session_id, self.dataset_sha256))
        return {'session_id': session_id, 'memory': self.read(session_id)}

    def _read(self, database, session_id):
        row = database.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise BackendError('session_not_found', 'Session not found', 404)
        if row['dataset_sha256'] != self.dataset_sha256:
            raise BackendError('session_graph_mismatch', 'Create a new session for this graph snapshot', 409)
        decisions = database.execute('SELECT person_id,decision FROM decisions WHERE session_id=? ORDER BY person_id', (session_id,)).fetchall()
        return {'version': row['version'], 'shortlisted_person_ids': [item['person_id'] for item in decisions if item['decision'] == 'shortlist'],
                'rejected_person_ids': [item['person_id'] for item in decisions if item['decision'] == 'reject'],
                'last_query': row['last_query'], 'last_intent': json.loads(row['last_intent_json']) if row['last_intent_json'] else None,
                'last_result_ids': json.loads(row['last_results_json'])}

    def read(self, session_id):
        with closing(self._connect()) as database:
            return self._read(database, session_id)

    def cached(self, session_id, request_id, digest):
        with closing(self._connect()) as database:
            self._read(database, session_id)
            row = database.execute('SELECT request_sha256,response_json FROM requests WHERE session_id=? AND request_id=?',
                                   (session_id, request_id)).fetchone()
            if row is not None:
                if row['request_sha256'] != digest:
                    raise BackendError('idempotency_conflict', 'Request ID was already used for different input', 409)
                return json.loads(row['response_json'])
        return None

    def commit(self, session_id, expected_version, request_id, digest, response_factory,
               context=None, decision=None, clear=False):
        with closing(self._connect()) as database, database:
            database.execute('BEGIN IMMEDIATE')
            previous = self._read(database, session_id)
            cached = database.execute('SELECT request_sha256,response_json FROM requests WHERE session_id=? AND request_id=?',
                                      (session_id, request_id)).fetchone()
            if cached:
                if cached['request_sha256'] != digest:
                    raise BackendError('idempotency_conflict', 'Request ID was already used for different input', 409)
                return json.loads(cached['response_json'])
            if previous['version'] != expected_version:
                raise BackendError('stale_memory', 'Session changed; read its memory and retry with the current version', 409)
            changed = context is not None or decision is not None or clear
            if clear:
                database.execute('DELETE FROM decisions WHERE session_id=?', (session_id,))
                # Old cached turns must not retain or resurrect forgotten content.
                database.execute('DELETE FROM requests WHERE session_id=?', (session_id,))
                database.execute("UPDATE sessions SET last_query=NULL,last_intent_json=NULL,last_results_json='[]' WHERE id=?", (session_id,))
            if decision is not None:
                person_id, action = decision
                if action == 'clear':
                    database.execute('DELETE FROM decisions WHERE session_id=? AND person_id=?', (session_id, person_id))
                else:
                    database.execute('INSERT INTO decisions VALUES(?,?,?) ON CONFLICT(session_id,person_id) DO UPDATE SET decision=excluded.decision',
                                     (session_id, person_id, action))
            if context is not None:
                database.execute('UPDATE sessions SET last_query=?,last_intent_json=?,last_results_json=? WHERE id=?',
                                 (context['query'], json.dumps(context['intent']), json.dumps(context['result_ids']), session_id))
            if changed:
                database.execute('UPDATE sessions SET version=version+1 WHERE id=?', (session_id,))
            memory = self._read(database, session_id)
            response = response_factory(memory)
            database.execute('INSERT INTO requests VALUES(?,?,?,?)', (session_id, request_id, digest, json.dumps(response, ensure_ascii=False)))
            return response

    def delete_session(self, session_id):
        with closing(self._connect()) as database, database:
            self._read(database, session_id)
            # Conversation tables are created lazily by the independent chat API.
            if database.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'").fetchone():
                database.execute('DELETE FROM conversations WHERE session_id=?', (session_id,))
            database.execute('DELETE FROM sessions WHERE id=?', (session_id,))
