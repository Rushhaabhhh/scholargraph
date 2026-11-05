"""Load immutable research artifacts once; serialize shared SQLite/model access."""

import json
import re
import sqlite3
import threading
from pathlib import Path

from ..assistant.grounding import GroundingVerifier, claim_text
from ..data.artifacts import digest_file
from ..assistant.memory import SessionStore
from ..assistant.providers import LocalLLMProvider, QueryUnderstander, RecordedProvider, UnavailableProvider
from ..assistant.safety import injection_like
from ..assistant.schemas import PathArgs, ProfileArgs, SearchExpertsArgs
from ..assistant.errors import BackendError
from ..graph.build import validate_graph
from ..graph.queries import GraphQueries
from ..ranking.scoring import score_model
from ..retrieval.encoder import LocalEncoder
from ..retrieval.index import tokens
from ..retrieval.factory import search_index


class Backend:
    def __init__(self, database, engine, model, session_store, understander=None):
        self.database, self.engine, self.model = database, engine, model
        self.sessions = session_store
        self.understander = understander or QueryUnderstander()
        self.graph = GraphQueries(database)
        self.verifier = GroundingVerifier(database)
        self.lock = threading.RLock()
        if self.model['encoder_sha256'] != engine.encoder.signature:
            raise ValueError('Reranker and encoder do not match')

    @classmethod
    def load(cls, config_path, session_db_override=None):
        config_path = Path(config_path).resolve()
        config = json.loads(config_path.read_text())
        def path(name):
            value = Path(config[name])
            return value if value.is_absolute() else (config_path.parent / value).resolve()
        state_path = Path(session_db_override).resolve() if session_db_override else path('session_db')
        if (state_path == path('graph') or state_path == path('model')
                or state_path.is_relative_to(path('index')) or state_path.is_relative_to(path('encoder'))):
            raise ValueError('Session storage must be separate from immutable research artifacts')
        database = sqlite3.connect(f'file:{path("graph")}?mode=ro', uri=True, check_same_thread=False)
        database.row_factory = sqlite3.Row
        database.execute('PRAGMA foreign_keys=ON')
        database.execute('PRAGMA query_only=ON')
        engine = None
        try:
            validate_graph(database)
            encoder = LocalEncoder(path('encoder'))
            model = json.loads(path('model').read_text())
            engine = search_index(database, path('index'), encoder, model,
                                  profiles=path('profiles') if 'profiles' in config else None,
                                  cross_directory=path('cross_encoder') if 'cross_encoder' in config else None)
            mode = config.get('query_provider', 'recorded')
            if mode == 'recorded':
                try:
                    provider = RecordedProvider(path('recordings'))
                except (OSError, ValueError, KeyError, TypeError):
                    provider = UnavailableProvider()
            elif mode == 'local_llm':
                provider = LocalLLMProvider(path('local_model'), config.get('local_model_sha256'))
            elif mode == 'fallback':
                provider = None
            else:
                raise ValueError('Unknown query-provider mode')
            runtime = cls(database, engine, model,
                          SessionStore(state_path, engine.manifest['content_sha256']), QueryUnderstander(provider))
            runtime.model_sha256 = digest_file(path('model'))
            return runtime
        except BaseException:
            if engine:
                engine.close()
            database.close()
            raise

    def close(self):
        with self.lock:
            self.engine.close()
            self.database.close()

    def search(self, arguments, memory=None):
        args = SearchExpertsArgs.model_validate(arguments)
        if injection_like(args.query):
            raise BackendError('blocked_input', 'Remove embedded instructions from the research query')
        understood = self.understander.understand(args.query)
        intent = understood['intent']
        # Explicit structured request fields override extracted preferences.
        if args.recency_preference is not None:
            intent['recency_preference'] = args.recency_preference
            if args.recency_preference == 'any':
                intent['since_year'] = None
        if args.since_year is not None:
            intent['since_year'] = args.since_year
        elif args.recency_preference != 'any':
            relative = re.search(r'\b(?:past|last)\s+([1-9]\d?)\s+years?\b', args.query, re.I)
            if relative:
                intent['recency_preference'] = 'recent'
                intent['since_year'] = max(1, self.engine.anchor_year - int(relative[1]) + 1)
        retrieval_query = ' '.join(intent['topics'])
        vector = self.engine.encoder.encode([retrieval_query])[0]
        retrieved = self.engine.retrieve(retrieval_query, vector)
        scores = score_model(retrieved['features'], self.model)
        memory = memory or {'shortlisted_person_ids': [], 'rejected_person_ids': []}
        rejected, shortlisted = set(memory['rejected_person_ids']), set(memory['shortlisted_person_ids'])
        minimum_year = intent['since_year']
        if minimum_year is None and intent['recency_preference'] == 'recent':
            minimum_year = max(1, self.engine.anchor_year - 5)
        keep, rejected_applied = [], []
        for index, identifier in enumerate(retrieved['author_ids']):
            if identifier in rejected:
                rejected_applied.append(identifier)
                continue
            if minimum_year is not None:
                papers = [paper for paper in self.engine.author_papers[identifier]
                          if self.engine.papers[paper]['year'] is not None and self.engine.papers[paper]['year'] >= minimum_year]
                if not papers:
                    continue
                papers.sort(key=lambda paper: (-float(self.engine.vectors[paper] @ vector), self.engine.papers[paper]['id']))
                retrieved['evidence'][identifier] = papers[:3]
            keep.append(index)
        filtered = dict(retrieved, author_ids=[retrieved['author_ids'][index] for index in keep])
        results = self.verifier.explain(self.engine.results(retrieval_query, filtered, scores[keep], args.limit))
        for result in results:
            result['shortlisted'] = result['person_id'] in shortlisted
        return {'query': args.query, 'retrieval_query': retrieval_query, 'results': results, 'understanding': understood,
                'effective_filters': {'since_year': minimum_year, 'graph_cutoff_year': self.engine.anchor_year},
                'applied_decisions': {'rejected_people_filtered': sorted(rejected_applied),
                                      'shortlisted_people_marked': [item['person_id'] for item in results if item['shortlisted']]}}

    def profile(self, arguments):
        args = ProfileArgs.model_validate(arguments)
        if args.person_id not in self.engine.authors:
            raise BackendError('author_not_found', 'Author not found', 404)
        profile = self.graph.profile(args.person_id)
        claims = [self.verifier.authorship(args.person_id, paper['paper_id']) for paper in profile['publications'][:10]]
        terms = {}
        for paper in profile['publications']:
            for term in sorted(tokens(paper['title'])):
                terms.setdefault(term, []).append(paper)
        topics = []
        for term, papers in sorted(terms.items(), key=lambda item: (-len(item[1]), item[0]))[:8]:
            paper = papers[0]
            claim = self.verifier.verify({'kind': 'title_term', 'person_id': args.person_id, 'paper_id': paper['paper_id'],
                                          'year': paper['year'], 'term': term, 'text': claim_text('title_term', paper, term=term)})
            claims.append(claim)
            topics.append({'topic': term, 'source_paper_ids': [item['paper_id'] for item in papers], 'supported': claim['supported']})
        return dict(profile, topics=topics, topic_method='Terms in publication titles; not independently inferred expertise.', claims=claims)

    def path(self, arguments):
        args = PathArgs.model_validate(arguments)
        for identifier in (args.source, args.target):
            if identifier not in self.engine.authors:
                raise BackendError('author_not_found', 'Author not found', 404)
        path = self.graph.collaboration_path(args.source, args.target, args.max_hops)
        claims = []
        for edge in path['edges']:
            paper = edge['evidence'][0]
            claims.append(self.verifier.verify({'kind': 'coauthorship', 'person_id': edge['from'], 'paper_id': paper['paper_id'],
                                                'collaborator_id': edge['to'], 'year': paper['year'],
                                                'text': claim_text('coauthorship', paper, edge['to'])}))
        return dict(path, claims=claims)

    def execute_tool(self, name, arguments, memory=None):
        # A closed registry and strict argument models are the execution authority.
        if name == 'search_experts':
            return self.search(SearchExpertsArgs.model_validate(arguments).model_dump(), memory)
        if name == 'get_profile':
            return self.profile(ProfileArgs.model_validate(arguments).model_dump())
        if name == 'find_collaboration_path':
            return self.path(PathArgs.model_validate(arguments).model_dump())
        raise BackendError('unknown_tool', 'Tool is not available')
