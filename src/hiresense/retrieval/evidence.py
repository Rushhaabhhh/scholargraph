"""Evidence-first author retrieval with lexical documents and multiple topic profiles."""
import json
import math
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from ..data.artifacts import digest_file, write_json
from .hybrid import HYBRID_FEATURES
from .index import SearchIndex, tokens

EVIDENCE_FEATURES = HYBRID_FEATURES + (
    'author_lexical_max', 'author_lexical_rank', 'evidence_idf_mean', 'evidence_term_support',
    'cross_logit_max', 'cross_logit_mean', 'cross_scored_fraction', 'topic_profile_count')


def _top(values, count):
    count = min(count, len(values))
    if not count:
        return np.empty(0, dtype=np.int64)
    ids = np.argpartition(-values, count - 1)[:count]
    return ids[np.lexsort((ids, -values[ids]))]


class EvidenceIndex(SearchIndex):
    feature_names = EVIDENCE_FEATURES

    def __init__(self, database, directory, encoder, *, profiles, cross_encoder=None,
                 paper_limit=1024, candidate_limit=800, profile_limit=256,
                 author_lexical_limit=256, expansion_limit=64, cross_paper_limit=192,
                 cross_author_limit=192, topic_profiles=3, query_adapter=None):
        super().__init__(database, directory, encoder, paper_limit, candidate_limit)
        if min(profile_limit, author_lexical_limit, expansion_limit, cross_paper_limit, cross_author_limit) < 0:
            raise ValueError('Evidence retrieval budgets must be nonnegative')
        if not 1 <= topic_profiles <= 8:
            raise ValueError('Use one to eight topic profiles')
        from .adaptation import QueryAdapter
        self.query_adapter = QueryAdapter(query_adapter, encoder.dimensions) if query_adapter is not None else None
        self.profile_limit, self.author_lexical_limit = profile_limit, author_lexical_limit
        self.expansion_limit, self.cross_paper_limit = expansion_limit, cross_paper_limit
        self.cross_author_limit, self.topic_profiles, self.cross_encoder = cross_author_limit, topic_profiles, cross_encoder
        self.author_ids = np.asarray(sorted(self.authors), dtype=np.int64)
        self.author_positions = {int(a): i for i, a in enumerate(self.author_ids)}
        frequency = Counter(t for ts in self.title_tokens for t in ts)
        self.idf = {t: math.log1p(len(self.papers) / (1 + n)) for t, n in frequency.items()}
        with threadpool_limits(limits=2, user_api='blas'):
            self._build_profiles(Path(profiles))
        self.retrieval_signature = {'version': 2, 'policy': 'evidence-first-v2',
            'profile_limit': profile_limit, 'author_lexical_limit': author_lexical_limit,
            'expansion_limit': expansion_limit, 'cross_paper_limit': cross_paper_limit,
            'cross_author_limit': cross_author_limit, 'profiles_sha256': self.profile_signature,
            'implementation_sha256': digest_file(__file__),
            'cross_implementation_sha256': digest_file(Path(__file__).with_name('crossencoder.py')),
            'query_adapter_sha256': self.query_adapter.signature if self.query_adapter else None,
            'adapter_implementation_sha256': digest_file(Path(__file__).with_name('adaptation.py')),
            'cross_encoder_sha256': cross_encoder.signature if cross_encoder else None}

    def _build_profiles(self, directory):
        signature = {'content': self.manifest['content_sha256'], 'encoder': self.encoder.signature,
                     'policy': 'recent-and-spaced-history,farthest-seeds,2-refinements,v2',
                     'topic_profiles': self.topic_profiles, 'sparse_authors': 'paper-channel-only', 'cutoff': self.anchor_year}
        if not directory.exists():
            directory.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(dir=directory.parent, prefix='.author-evidence-'))
            try:
                # At most K profiles per author, written on disk rather than retained as Python vectors.
                allocations = [min(self.topic_profiles, max(1, min(48, len(self.author_papers[int(a)]))//4))
                               if len(self.author_papers[int(a)]) >= 3 else 0 for a in self.author_ids]
                values = np.lib.format.open_memmap(stage / 'vectors.npy', mode='w+', dtype=np.float32,
                    shape=(sum(allocations), self.encoder.dimensions))
                owners, counts = [], []
                lexical = sqlite3.connect(stage / 'lexical.sqlite3')
                lexical.execute("CREATE VIRTUAL TABLE authors USING fts5(titles, tokenize='porter unicode61 remove_diacritics 2')")
                offset = 0
                for row, author in enumerate(self.author_ids):
                    ordered = sorted(self.author_papers[int(author)], key=lambda i: (-(self.papers[i]['year'] or 0), self.papers[i]['id']))
                    # Preserve recent work and a deterministic sample of older specialist evidence.
                    chosen = ordered[:12]
                    tail = ordered[12:]
                    if tail:
                        chosen += [tail[int(i)] for i in np.linspace(0, len(tail)-1, min(36, len(tail)), dtype=int)]
                    matrix = np.asarray(self.vectors[chosen])
                    k = allocations[row]
                    seeds = [0] if k else []
                    while len(seeds) < k:
                        distances = 1 - (matrix @ matrix[seeds].T).max(axis=1)
                        distances[seeds] = -1
                        seeds.append(int(np.argmax(distances)))
                    centers = matrix[seeds].copy()
                    for _ in range(2 if k else 0):
                        assignment = np.argmax(matrix @ centers.T, axis=1)
                        for j in range(k):
                            members = matrix[assignment == j]
                            if len(members):
                                value = members.mean(axis=0)
                                centers[j] = value / max(float(np.linalg.norm(value)), 1e-9)
                    representatives = list(range(min(4, len(chosen))))
                    for center in centers:
                        representatives.extend(_top(matrix @ center, 3).tolist())
                    representatives = list(dict.fromkeys(representatives))[:12]
                    lexical.execute('INSERT INTO authors(rowid,titles) VALUES(?,?)',
                        (row+1, ' '.join(self.papers[chosen[j]]['title'] for j in representatives)))
                    values[offset:offset+k] = centers
                    owners.extend([row]*k)
                    counts.append(k)
                    offset += k
                lexical.commit()
                lexical.close()
                values.flush()
                del values
                # Unused rows remain outside profile_owners and never participate in search.
                np.save(stage / 'owners.npy', np.asarray(owners, dtype=np.int64), allow_pickle=False)
                np.save(stage / 'counts.npy', np.asarray(counts, dtype=np.int16), allow_pickle=False)
                write_json(stage / 'manifest.json', {'signature': signature,
                    'author_ids': self.author_ids.tolist(), 'profiles': offset,
                    'files': {p:digest_file(stage/p) for p in ('vectors.npy','owners.npy','counts.npy','lexical.sqlite3')}})
                stage.rename(directory)
            except BaseException:
                shutil.rmtree(stage)
                raise
        metadata = json.loads((directory/'manifest.json').read_text())
        if metadata['signature'] != signature or metadata['author_ids'] != self.author_ids.tolist():
            raise ValueError('Stale evidence profile index')
        if any(digest_file(directory/p) != v for p,v in metadata['files'].items()):
            raise ValueError('Corrupted evidence profile index')
        self.profile_vectors = np.load(directory/'vectors.npy', mmap_mode='r', allow_pickle=False)[:metadata['profiles']]
        self.profile_owners = np.load(directory/'owners.npy', allow_pickle=False)
        self.profile_counts = np.load(directory/'counts.npy', allow_pickle=False)
        if len(self.profile_vectors) != len(self.profile_owners) or len(self.profile_counts) != len(self.author_ids):
            raise ValueError('Invalid evidence profile dimensions')
        self.author_lexical = sqlite3.connect(f'file:{(directory/"lexical.sqlite3").resolve()}?mode=ro', uri=True, check_same_thread=False)
        self.profile_signature = digest_file(directory/'manifest.json')

    def close(self):
        if hasattr(self, 'author_lexical'):
            self.author_lexical.close()
        super().close()

    def _author_lexical(self, query):
        terms = sorted(tokens(query))[:64]
        if not terms or not self.author_lexical_limit:
            return []
        expression = ' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
        return [(int(self.author_ids[row-1]), -score) for row,score in self.author_lexical.execute(
            'SELECT rowid,bm25(authors) score FROM authors WHERE authors MATCH ? ORDER BY score,rowid LIMIT ?',
            (expression,self.author_lexical_limit))]

    def retrieve(self, query, vector=None, *, since_year=None, excluded_ids=()):
        if not isinstance(query,str) or len(query)>4000:
            raise ValueError('Query must be a string of at most 4000 characters')
        empty = {'author_ids': [], 'features': np.empty((0,len(self.feature_names)),dtype=np.float32),
                 'lexical': [], 'dense': [], 'hybrid': [], 'evidence': {}}
        if not query.strip() or not self.papers:
            return empty
        vector = self.encoder.encode([query])[0] if vector is None else vector
        if self.query_adapter is not None:
            vector = self.query_adapter.transform(vector)
        context = self.candidate_context(query,vector,since_year=since_year)
        excluded = set(excluded_ids)
        def eligible(a):
            return a not in excluded and (since_year is None or any(
                self.papers[i]['year'] is not None and self.papers[i]['year'] >= since_year for i in self.author_papers[a]))
        profile_scores = np.full(len(self.author_ids),-1,dtype=np.float32)
        if since_year is not None:
            # A date-filtered request must not score a person's old topic profile.
            for a in context['fused']:
                values = [float(context['similarities'][i]) for i in self.author_papers[a]
                          if self.papers[i]['year'] is not None and self.papers[i]['year'] >= since_year]
                if values:
                    profile_scores[self.author_positions[a]] = max(values)
        elif self.profile_limit:
            with threadpool_limits(limits=2,user_api='blas'):
                similarities = np.asarray(self.profile_vectors @ vector,dtype=np.float32)
            np.maximum.at(profile_scores,self.profile_owners,similarities)
        selected = [row for row in _top(profile_scores,self.profile_limit) if profile_scores[row] > -1]
        profile_rank = {int(self.author_ids[row]):rank for rank,row in enumerate(selected,1) if eligible(int(self.author_ids[row]))}
        if since_year is None:
            author_lexical = [(a,s) for a,s in self._author_lexical(query) if eligible(a)]
        else:
            author_lexical = [(a,max((context['lexical_scores'].get(i,0) for i in self.author_papers[a]),default=0))
                              for a in context['lexical'] if eligible(a)]
            author_lexical = author_lexical[:self.author_lexical_limit]
        author_lex_scores = dict(author_lexical)
        author_lex_rank = {a:r for r,(a,_) in enumerate(author_lexical,1)}
        for ranks,weight in ((profile_rank,0.75),(author_lex_rank,0.75)):
            for a,rank in ranks.items():
                context['fused'][a] = context['fused'].get(a,0)+weight/(60+rank)
        graph_support = defaultdict(float)
        if self.expansion_limit:
            seeds = sorted(context['fused'],key=lambda a:(-context['fused'][a],a))[:24]
            for seed in seeds:
                indices = [i for i in self.author_papers[seed] if self.papers[i]['year'] is not None
                           and self.papers[i]['year'] <= self.anchor_year
                           and (since_year is None or self.papers[i]['year']>=since_year)]
                for i in sorted(indices,key=lambda i:-float(context['similarities'][i]))[:3]:
                    if context['similarities'][i] < .35:
                        continue
                    weight = float(context['similarities'][i])*math.exp(-(self.anchor_year-self.papers[i]['year'])/10)
                    for other in self.paper_authors[i]:
                        if other!=seed and eligible(other):
                            graph_support[other] += weight/math.sqrt(1+self.degree[other])
            for rank,a in enumerate(sorted(graph_support,key=lambda a:(-graph_support[a],a))[:self.expansion_limit],1):
                context['fused'][a] = context['fused'].get(a,0)+.15/(60+rank)
        authors = sorted((a for a in context['fused'] if eligible(a)),key=lambda a:(-context['fused'][a],a))[:self.candidate_limit]
        if not authors:
            return empty
        result = self.assemble(query,authors,context)
        terms = tokens(query)
        denominator = sum(self.idf.get(t,1) for t in terms) or 1
        words = query.casefold().split()
        bigrams = list(zip(words,words[1:]))
        evidence_coverage = {}
        for a in authors:
            indices = [i for i in self.author_papers[a] if since_year is None or
                       (self.papers[i]['year'] is not None and self.papers[i]['year'] >= since_year)]
            coverage = {i: sum(self.idf.get(t,1) for t in terms & self.title_tokens[i])/denominator for i in indices}
            supporting = sorted(indices, key=lambda i: (-(coverage[i]+.35*float(context['similarities'][i])), self.papers[i]['id']))[:3]
            result['evidence'][a] = supporting
            evidence_coverage[a] = [coverage[i] for i in supporting]
        # Choose the neural shortlist by actual evidence, with deterministic ties.
        shortlist = sorted(authors,key=lambda a:(-(evidence_coverage[a][0]+.35*float(
            context['similarities'][result['evidence'][a][0]])+.1*(60/(60+author_lex_rank[a]) if a in author_lex_rank else 0)),a))
        shortlist = shortlist[:min(self.cross_author_limit,self.cross_paper_limit)]
        pairs,seen = [],set()
        for slot in range(2):
            for a in shortlist:
                evidence = result['evidence'][a]
                if slot<len(evidence) and evidence[slot] not in seen and len(pairs)<self.cross_paper_limit:
                    pairs.append(evidence[slot]);seen.add(evidence[slot])
        raw = {}
        if self.cross_encoder is not None and pairs:
            raw = dict(zip(pairs,map(float,self.cross_encoder.score(query,[self.papers[i]['title'] for i in pairs]))))
        max_lex = max(author_lex_scores.values(),default=1) or 1
        extras = []
        for author_row,a in enumerate(authors):
            indices = [i for i in self.author_papers[a] if since_year is None or
                       (self.papers[i]['year'] is not None and self.papers[i]['year']>=since_year)]
            coverage = [sum(self.idf.get(t,1) for t in terms & self.title_tokens[i])/denominator for i in indices]
            scored = sorted([raw[i] for i in result['evidence'][a] if i in raw],reverse=True)
            probabilities = [1/(1+math.exp(-max(-30,min(30,v)))) for v in scored]
            phrase = max((sum(' '.join(p) in self.papers[i]['title'].casefold() for p in bigrams)/max(1,len(bigrams)) for i in indices),default=0)
            extras.append([max(float(profile_scores[self.author_positions[a]]),float(context['similarities'][result['evidence'][a][0]])),60/(60+profile_rank[a]) if a in profile_rank else 0,
                graph_support[a],max(coverage,default=0),phrase,
                probabilities[0] if scored else 0, sum(probabilities[:2])/min(2,len(scored)) if scored else 0,float(bool(scored)),
                author_lex_scores.get(a,0)/max_lex,60/(60+author_lex_rank[a]) if a in author_lex_rank else 0,
                float(np.mean(sorted(coverage,reverse=True)[:3])),sum(v>.2 for v in coverage)/len(coverage),
                scored[0] if scored else -30,float(np.mean(scored[:2])) if scored else -30,
                len(scored)/len(result['evidence'][a]),float(self.profile_counts[self.author_positions[a]])])
            result['evidence'][a].sort(key=lambda i:(-raw.get(i,-math.inf),-float(context['similarities'][i]),i))
            year = self.papers[result['evidence'][a][0]]['year']
            result['features'][author_row,7] = math.exp(-max(0,self.anchor_year-year)/5) if year else 0
        result['features'] = np.concatenate((result['features'],np.asarray(extras,dtype=np.float32)),axis=1)
        result['diagnostics'] = {'neural_shortlist':shortlist,'scored_papers':len(raw),
            'neural_coverage':sum(bool(result['features'][i,19]) for i in range(len(authors))),
            'channels':{'author_lexical':len(author_lexical),'topic_profiles':len(profile_rank),'graph_expansion':len(graph_support)}}
        return result
