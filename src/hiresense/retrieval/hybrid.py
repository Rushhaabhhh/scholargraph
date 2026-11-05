"""Hybrid candidate retrieval, historical author profiles and neural evidence scores."""

import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from ..data.artifacts import digest_file, write_json
from .index import FEATURE_NAMES, SearchIndex, tokens

HYBRID_FEATURES = FEATURE_NAMES + ('profile_similarity', 'profile_rank', 'graph_support',
                                 'title_idf_coverage', 'bigram_coverage',
                                 'cross_max', 'cross_top2', 'cross_observed')


class HybridIndex(SearchIndex):
    feature_names = HYBRID_FEATURES

    def __init__(self, database, directory, encoder, *, profiles, cross_encoder=None,
                 paper_limit=512, candidate_limit=400, profile_limit=128,
                 expansion_limit=64, cross_paper_limit=64):
        super().__init__(database, directory, encoder, paper_limit, candidate_limit)
        if min(profile_limit, expansion_limit, cross_paper_limit) < 0:
            raise ValueError('Hybrid retrieval limits must be nonnegative')
        self.profile_limit, self.expansion_limit = profile_limit, expansion_limit
        self.cross_paper_limit, self.cross_encoder = cross_paper_limit, cross_encoder
        self.profile_ids = np.asarray(sorted(self.authors), dtype=np.int64)
        self.profile_positions = {int(a): i for i, a in enumerate(self.profile_ids)}
        self._profiles(Path(profiles))
        frequencies = Counter(term for terms in self.title_tokens for term in terms)
        self.idf = {term: math.log(1 + len(self.papers) / (1 + count)) for term, count in frequencies.items()}
        self.retrieval_signature = {'version': 1, 'profile_limit': profile_limit, 'expansion_limit': expansion_limit,
                                    'cross_paper_limit': cross_paper_limit,
                                    'profiles_sha256': self.profile_signature,
                                    'cross_encoder_sha256': cross_encoder.signature if cross_encoder else None}

    def _profiles(self, directory):
        signature = {'content': self.manifest['content_sha256'], 'encoder': self.encoder.signature,
                     'policy': 'latest-10-papers,exp-age/10,normalized-mean-v1', 'cutoff': self.anchor_year}
        if not directory.exists():
            directory.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(dir=directory.parent, prefix='.profiles-'))
            try:
                values = np.lib.format.open_memmap(stage / 'vectors.npy', mode='w+', dtype=np.float32,
                                                   shape=(len(self.profile_ids), self.encoder.dimensions))
                for row, author in enumerate(self.profile_ids):
                    indices = sorted(self.author_papers[int(author)],
                                     key=lambda i: (-(self.papers[i]['year'] or 0), self.papers[i]['id']))[:10]
                    weights = np.asarray([math.exp(-max(0, self.anchor_year - (self.papers[i]['year'] or 0)) / 10)
                                          for i in indices], dtype=np.float32)
                    value = (self.vectors[indices] * weights[:, None]).sum(axis=0)
                    values[row] = value / max(float(np.linalg.norm(value)), 1e-9)
                values.flush()
                del values
                write_json(stage / 'manifest.json', {'signature': signature,
                           'vectors_sha256': digest_file(stage / 'vectors.npy'), 'author_ids': self.profile_ids.tolist()})
                stage.rename(directory)
            except BaseException:
                shutil.rmtree(stage)
                raise
        metadata = json.loads((directory / 'manifest.json').read_text())
        if (metadata['signature'] != signature or metadata['author_ids'] != self.profile_ids.tolist()
                or metadata['vectors_sha256'] != digest_file(directory / 'vectors.npy')):
            raise ValueError('Stale or corrupted author profile index')
        self.profile_vectors = np.load(directory / 'vectors.npy', mmap_mode='r', allow_pickle=False)
        if self.profile_vectors.shape != (len(self.authors), self.encoder.dimensions):
            raise ValueError('Invalid author profile shape')
        self.profile_signature = digest_file(directory / 'manifest.json')

    def retrieve(self, query, vector=None, *, since_year=None, excluded_ids=()):
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError('Query must be a string of at most 4000 characters')
        if not query.strip() or not self.papers:
            return {'author_ids': [], 'features': np.empty((0, len(self.feature_names))),
                    'lexical': [], 'dense': [], 'hybrid': [], 'evidence': {}}
        vector = self.encoder.encode([query])[0] if vector is None else vector
        context = self.candidate_context(query, vector, since_year=since_year)
        with threadpool_limits(limits=2, user_api='blas'):
            profile_scores = np.asarray(self.profile_vectors @ vector, dtype=np.float32)
        count = min(self.profile_limit, len(self.profile_ids))
        selected = np.argsort(-profile_scores, kind='stable')[:count]
        profile_rank = {int(self.profile_ids[row]): rank for rank, row in enumerate(selected, 1)
                        if any(since_year is None or (self.papers[i]['year'] is not None and self.papers[i]['year'] >= since_year)
                               for i in self.author_papers[int(self.profile_ids[row])])}
        for author, rank in profile_rank.items():
            context['fused'][author] = context['fused'].get(author, 0.0) + 0.5 / (60 + rank)
        graph_support = defaultdict(float)
        seeds = sorted(context['fused'], key=lambda a: (-context['fused'][a], a))[:16]
        for seed in seeds:
            # Only sourced, historical coauthorship events in topically matching papers.
            dated = [i for i in self.author_papers[seed]
                     if self.papers[i]['year'] is not None and self.papers[i]['year'] <= self.anchor_year
                     and (since_year is None or self.papers[i]['year'] >= since_year)]
            relevant_papers = sorted(dated, key=lambda i: (-context['similarities'][i], i))[:3]
            for i in relevant_papers:
                if float(context['similarities'][i]) < 0.25:
                    continue
                for other in self.paper_authors[i]:
                    if other != seed:
                        graph_support[other] += float(context['similarities'][i]) / math.sqrt(1 + self.degree[other])
        expanded = sorted(graph_support, key=lambda a: (-graph_support[a], a))[:self.expansion_limit]
        for rank, author in enumerate(expanded, 1):
            context['fused'][author] = context['fused'].get(author, 0.0) + 0.15 / (60 + rank)
        excluded = set(excluded_ids)
        authors = sorted((a for a in context['fused'] if a not in excluded), key=lambda a: (-context['fused'][a], a))[:self.candidate_limit]
        retrieved = self.assemble(query, authors, context)
        if not authors:
            retrieved['features'] = np.empty((0, len(self.feature_names)), dtype=np.float32)
            return retrieved
        query_terms = tokens(query)
        denominator = sum(self.idf.get(t, 1.0) for t in query_terms) or 1
        words = query.lower().split()
        bigrams = list(zip(words, words[1:]))
        pair_indices = []
        for author in authors:
            for i in retrieved['evidence'][author][:2]:
                if i not in pair_indices and len(pair_indices) < self.cross_paper_limit:
                    pair_indices.append(i)
        cross = {}
        if self.cross_encoder is not None and pair_indices:
            logits = self.cross_encoder.score(query, [self.papers[i]['title'] for i in pair_indices])
            cross = {i: float(1 / (1 + math.exp(-float(np.clip(value, -30, 30)))))
                     for i, value in zip(pair_indices, logits)}
        extras = []
        for author in authors:
            indices = [i for i in self.author_papers[author] if since_year is None or
                       (self.papers[i]['year'] is not None and self.papers[i]['year'] >= since_year)]
            scored = sorted((cross[i] for i in retrieved['evidence'][author] if i in cross), reverse=True)
            coverage = max((sum(self.idf.get(t, 1.0) for t in query_terms & self.title_tokens[i]) / denominator
                            for i in indices), default=0.0)
            phrase = max((sum((' '.join(pair) in self.papers[i]['title'].lower()) for pair in bigrams)
                          / max(1, len(bigrams)) for i in indices), default=0.0)
            extras.append([float(profile_scores[self.profile_positions[author]]),
                           60 / (60 + profile_rank[author]) if author in profile_rank else 0,
                           graph_support[author], coverage, phrase,
                           scored[0] if scored else 0, sum(scored[:2]) / min(2, len(scored)) if scored else 0,
                           float(bool(scored))])
            retrieved['evidence'][author].sort(key=lambda i: (-cross.get(i, -1), -float(context['similarities'][i]), i))
        retrieved['features'] = np.concatenate((retrieved['features'], np.asarray(extras, dtype=np.float32)), axis=1)
        return retrieved
