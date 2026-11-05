"""Paper-level BM25 and local dense retrieval, aggregated to expert candidates."""

import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path
from time import monotonic

import numpy as np
from threadpoolctl import threadpool_limits

from ..data.artifacts import digest_file, write_json
from ..evaluation.split import assert_no_leakage
from .encoder import LocalEncoder

_STOP = frozenset('a an and are as at be by for from how in into is it of on or that the their this to using we with'.split())
FEATURE_NAMES = ('lexical_max', 'dense_max', 'dense_top3', 'lexical_rank', 'dense_rank', 'title_coverage',
                 'support_fraction', 'matched_recency', 'author_recency', 'log_publications', 'log_collaborators', 'hybrid_rrf')
FEATURE_GROUPS = {'dense': ('dense_max', 'dense_top3', 'dense_rank'),
                  'recency': ('matched_recency', 'author_recency'),
                  'breadth_graph': ('support_fraction', 'log_publications', 'log_collaborators')}


def tokens(text):
    return {word for word in re.findall(r'[^\W_]+', text.casefold(), flags=re.UNICODE)
            if len(word) > 1 and word not in _STOP}


def content_signature(database):
    """Bind artifacts to evidence and authorship, without using display names."""
    digest = hashlib.sha256()
    for sql in ('SELECT id,title,year,venue FROM papers ORDER BY id',
                'SELECT paper_id,author_id,author_position FROM paper_authors ORDER BY paper_id,author_position'):
        for row in database.execute(sql):
            digest.update(json.dumps(list(row), ensure_ascii=False).encode() + b'\n')
    return digest.hexdigest()


def build_index(database, directory: str | Path, encoder: LocalEncoder) -> dict:
    cutoff = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if cutoff:
        assert_no_leakage(database, [], [], int(cutoff[0]))
    target = Path(directory)
    if target.exists():
        raise ValueError('Index output must be a new directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=target.parent, prefix='.index-'))
    started = monotonic()
    try:
        paper_count = database.execute('SELECT COUNT(*) FROM papers').fetchone()[0]
        embeddings = np.lib.format.open_memmap(stage / 'embeddings.npy', mode='w+', dtype=np.float32,
                                               shape=(paper_count, encoder.dimensions))
        paper_ids = []
        lexical = sqlite3.connect(stage / 'lexical.sqlite3')
        try:
            lexical.execute("CREATE VIRTUAL TABLE documents USING fts5(title, tokenize='porter unicode61 remove_diacritics 2')")
            cursor = database.execute('SELECT id,title FROM papers ORDER BY id')
            offset = 0
            while batch := cursor.fetchmany(512):
                vectors = encoder.encode([row['title'] for row in batch])
                embeddings[offset:offset + len(batch)] = vectors
                lexical.executemany('INSERT INTO documents(rowid,title) VALUES(?,?)',
                                    ((offset + index + 1, paper['title']) for index, paper in enumerate(batch)))
                paper_ids.extend(row['id'] for row in batch)
                offset += len(batch)
            if offset != paper_count:
                raise ValueError('Paper count changed during index creation')
            lexical.commit()
        finally:
            lexical.close()
        embeddings.flush()
        del embeddings
        manifest = {'version': 1, 'content_sha256': content_signature(database), 'encoder_sha256': encoder.signature,
                    'paper_ids': paper_ids, 'dimensions': encoder.dimensions,
                    'files': {name: digest_file(stage / name) for name in ('embeddings.npy', 'lexical.sqlite3')}}
        write_json(stage / 'manifest.json', manifest)
        stage.rename(target)
        return {'papers': paper_count, 'elapsed_seconds': round(monotonic() - started, 3),
                'content_sha256': manifest['content_sha256'], 'encoder_sha256': encoder.signature}
    except BaseException:
        shutil.rmtree(stage)
        raise


class SearchIndex:
    def __init__(self, database, directory: str | Path, encoder: LocalEncoder,
                 paper_limit: int = 256, candidate_limit: int = 200):
        if paper_limit < 1 or candidate_limit < 1:
            raise ValueError('Retrieval limits must be positive')
        cutoff = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
        if cutoff:
            assert_no_leakage(database, [], [], int(cutoff[0]))
        self.database, self.encoder = database, encoder
        self.paper_limit, self.candidate_limit = paper_limit, candidate_limit
        directory = Path(directory)
        self.manifest = json.loads((directory / 'manifest.json').read_text())
        if (self.manifest['content_sha256'] != content_signature(database)
                or self.manifest['encoder_sha256'] != encoder.signature):
            raise ValueError('Stale index: graph evidence or embedding encoder differs')
        for name, expected in self.manifest['files'].items():
            if digest_file(directory / name) != expected:
                raise ValueError(f'Index artifact checksum mismatch: {name}')
        self.vectors = np.load(directory / 'embeddings.npy', mmap_mode='r', allow_pickle=False)
        if self.vectors.shape != (len(self.manifest['paper_ids']), encoder.dimensions):
            raise ValueError('Invalid vector index shape')
        self.lexical = sqlite3.connect(f'file:{(directory / "lexical.sqlite3").resolve()}?mode=ro', uri=True, check_same_thread=False)
        self.papers = [dict(row) for row in database.execute('SELECT id,title,year FROM papers ORDER BY id')]
        if [row['id'] for row in self.papers] != self.manifest['paper_ids']:
            raise ValueError('Paper IDs differ from index manifest')
        self.paper_lookup = {paper['id']: index for index, paper in enumerate(self.papers)}
        self.authors = {row['id']: row['canonical_name'] for row in database.execute('SELECT id,canonical_name FROM authors')}
        self.paper_authors, self.author_papers = [[] for _ in self.papers], defaultdict(list)
        for row in database.execute('SELECT paper_id,author_id FROM paper_authors ORDER BY paper_id,author_position'):
            index = self.paper_lookup[row['paper_id']]
            self.paper_authors[index].append(row['author_id'])
            self.author_papers[row['author_id']].append(index)
        self.title_tokens = [tokens(paper['title']) for paper in self.papers]
        self.degree = defaultdict(int)
        for row in database.execute('''SELECT author,COUNT(DISTINCT collaborator) FROM (
            SELECT source_id author,target_id collaborator FROM context_edges WHERE edge_type='coauthorship'
            UNION ALL SELECT target_id,source_id FROM context_edges WHERE edge_type='coauthorship') GROUP BY author'''):
            self.degree[int(row[0].split(':')[1])] = row[1]
        cutoff = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
        self.anchor_year = int(cutoff[0]) if cutoff else max((paper['year'] or 0 for paper in self.papers), default=0)
        self.author_recency = {}
        for identifier, indices in self.author_papers.items():
            year = max((self.papers[index]['year'] or 0 for index in indices), default=0)
            self.author_recency[identifier] = math.exp(-max(0, self.anchor_year - year) / 5) if year else 0.0

    def close(self):
        self.lexical.close()

    def _lexical(self, query):
        query_terms = sorted(tokens(query))[:64]
        if not query_terms:
            return []
        expression = ' OR '.join('"' + token.replace('"', '""') + '"' for token in query_terms)
        return [(row[0] - 1, -row[1]) for row in self.lexical.execute(
            'SELECT rowid,bm25(documents) score FROM documents WHERE documents MATCH ? ORDER BY score,rowid LIMIT ?',
            (expression, self.paper_limit))]

    def retrieve(self, query: str, vector=None):
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError('Query must be a string of at most 4000 characters')
        if not query.strip() or not self.papers:
            return {'author_ids': [], 'features': np.empty((0, len(FEATURE_NAMES))), 'lexical': [], 'dense': [], 'hybrid': [], 'evidence': {}}
        vector = self.encoder.encode([query])[0] if vector is None else vector
        with threadpool_limits(limits=2, user_api='blas'):
            similarities = np.asarray(self.vectors @ vector, dtype=np.float32)
        count = min(self.paper_limit, len(self.papers))
        selected = np.argpartition(-similarities, count - 1)[:count]
        selected = sorted(selected, key=lambda index: (-float(similarities[index]), int(index)))
        lexical_papers = self._lexical(query)
        lexical_scores = dict(lexical_papers)
        def aggregate(paper_scores):
            values = {}
            for index, score in paper_scores:
                for author in self.paper_authors[index]:
                    values[author] = max(values.get(author, -math.inf), float(score))
            return sorted(values, key=lambda author: (-values[author], author))
        lexical = aggregate(lexical_papers)
        dense = aggregate((index, similarities[index]) for index in selected)
        lexical_rank = {identifier: rank for rank, identifier in enumerate(lexical, 1)}
        dense_rank = {identifier: rank for rank, identifier in enumerate(dense, 1)}
        fused = {identifier: 1 / (60 + lexical_rank[identifier]) if identifier in lexical_rank else 0.0
                 for identifier in set(lexical_rank) | set(dense_rank)}
        for identifier in dense_rank:
            fused[identifier] += 1 / (60 + dense_rank[identifier])
        author_ids = sorted(fused, key=lambda author: (-fused[author], author))[:self.candidate_limit]
        max_lexical = max(lexical_scores.values(), default=1.0)
        query_tokens = tokens(query)
        features, evidence = [], {}
        for identifier in author_ids:
            indices = self.author_papers[identifier]
            dense_values = sorted((float(similarities[index]) for index in indices), reverse=True)
            coverages = {index: len(query_tokens & self.title_tokens[index]) / max(1, len(query_tokens)) for index in indices}
            supporting = sorted(indices, key=lambda index: (-(lexical_scores.get(index, 0.0) / max_lexical + float(similarities[index])), self.papers[index]['id']))
            best_year = self.papers[supporting[0]]['year'] or 0
            features.append([
                max((lexical_scores.get(index, 0.0) / max_lexical for index in indices), default=0.0),
                dense_values[0], sum(dense_values[:3]) / min(3, len(dense_values)),
                60 / (60 + lexical_rank[identifier]) if identifier in lexical_rank else 0.0,
                60 / (60 + dense_rank[identifier]) if identifier in dense_rank else 0.0,
                max(coverages.values(), default=0.0),
                sum(coverage > 0 for coverage in coverages.values()) / len(indices),
                math.exp(-max(0, self.anchor_year - best_year) / 5) if best_year else 0.0,
                self.author_recency[identifier], math.log1p(len(indices)), math.log1p(self.degree[identifier]), fused[identifier] * 30,
            ])
            evidence[identifier] = supporting[:3]
        return {'author_ids': author_ids, 'features': np.asarray(features, dtype=np.float32).reshape(-1, len(FEATURE_NAMES)),
                'lexical': lexical[:self.candidate_limit], 'dense': dense[:self.candidate_limit],
                'hybrid': author_ids, 'evidence': evidence}

    def results(self, query, retrieval, scores, limit=10):
        ranked = sorted(zip(retrieval['author_ids'], scores), key=lambda pair: (-float(pair[1]), pair[0]))[:limit]
        output = []
        for identifier, score in ranked:
            evidence = []
            for index in retrieval['evidence'][identifier]:
                paper = self.papers[index]
                evidence.append({'paper_id': paper['id'], 'title': paper['title'], 'year': paper['year'], 'source': 'dblp',
                                 'collaborators': [{'person_id': other, 'name': self.authors[other]}
                                                   for other in self.paper_authors[index] if other != identifier]})
            output.append({'person_id': identifier, 'name': self.authors[identifier], 'score': float(score),
                           'explanation': f"Ranked using research-title relevance and historical publication evidence; {len(evidence)} supporting paper(s) shown.",
                           'evidence': evidence})
        return output
