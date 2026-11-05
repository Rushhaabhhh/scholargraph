"""Evaluate all temporal queries, including those with irretrievable new authors."""

import numpy as np

from ..ranking.scoring import score_model
from ..ranking.service import search
from .metrics import ranking_metrics
from ..retrieval.index import FEATURE_NAMES


def evaluate_rankings(engine, cache, models: dict, bootstrap_samples=1000, seed=42):
    schema = tuple(getattr(engine, 'feature_names', FEATURE_NAMES))
    scores = {}
    for name, model in models.items():
        columns = len(model['features'])
        if tuple(model['features']) != schema[:columns]:
            raise ValueError('Evaluation model features are not an ordered prefix of the retrieval schema')
        scores[name] = score_model(cache['features'][:, :columns], model)
    per_query = {name: [] for name in ('lexical', 'dense', 'hybrid', *models)}
    cohort = {'newcomer_history_1_or_2': [], 'prolific_history_20_plus': [], 'has_unseen_relevant_author': []}
    candidate_hits, retrievable_count, relevant_count, available_queries = 0, 0, 0, 0
    failures = {}
    known_ids = set(engine.authors)
    for index, query in enumerate(cache['queries']):
        start, end = cache['offsets'][index:index + 2]
        ids = cache['author_ids'][start:end]
        relevant = set(query.relevant_author_ids)
        known = relevant & known_ids
        candidate_hits += len(relevant & set(ids.tolist()))
        retrievable_count += len(known)
        relevant_count += len(relevant)
        available_queries += bool(known)
        orders = {'lexical': [int(value) for value in cache['lexical'][index] if value != -1],
                  'dense': [int(value) for value in cache['dense'][index] if value != -1], 'hybrid': ids.tolist()}
        for name, values in scores.items():
            orders[name] = ids[np.lexsort((ids, -values[start:end]))].tolist()
        for name, ranked in orders.items():
            per_query[name].append(ranking_metrics(ranked, relevant))
        history = [len(engine.author_papers[identifier]) for identifier in known]
        if any(count <= 2 for count in history):
            cohort['newcomer_history_1_or_2'].append(index)
        if any(count >= 20 for count in history):
            cohort['prolific_history_20_plus'].append(index)
        if relevant - known:
            cohort['has_unseen_relevant_author'].append(index)
        if 'learned' in orders and per_query['learned'][-1]['ndcg_at_10'] == 0:
            if not known:
                category = 'no_historical_evidence'
                change = 'Additional public pre-cutoff sources could improve coverage; future papers must remain excluded.'
            elif not relevant & set(ids.tolist()):
                category = 'candidate_retrieval_miss'
                change = 'Test larger retrieval budgets and author-level topic profiles using validation queries.'
            else:
                category = 'reranking_miss'
                change = 'Inspect topic specificity and sampled-negative ambiguity; validate richer paper-author relevance features.'
            failures.setdefault(category, {'query_id': query.query_id, 'query': query.text,
                                          'relevant_author_ids': sorted(relevant), 'retrievable_relevant_author_ids': sorted(known),
                                          'top_results': [{'person_id': identifier, 'name': engine.authors[identifier]}
                                                          for identifier in orders['learned'][:3]],
                                          'failure': category, 'proposed_change': change})
    def summarize(indices):
        return {name: {key: float(np.mean([values[index][key] for index in indices])) if indices else 0.0
                       for key in ('ndcg_at_10', 'mrr')} for name, values in per_query.items()}
    differences = {}
    if 'learned' in per_query and cache['queries']:
        rng = np.random.default_rng(seed)
        sample = rng.integers(0, len(cache['queries']), size=(bootstrap_samples, len(cache['queries'])))
        trained = np.asarray([row['ndcg_at_10'] for row in per_query['learned']])
        for baseline in ('lexical', 'dense', 'hybrid'):
            delta = trained - np.asarray([row['ndcg_at_10'] for row in per_query[baseline]])
            interval = np.quantile(delta[sample].mean(axis=1), [0.025, 0.975])
            differences[baseline] = {'mean_ndcg_delta': float(delta.mean()), 'paired_bootstrap_95pct': interval.tolist()}
    return {'queries': len(cache['queries']), 'metrics': summarize(list(range(len(cache['queries'])))),
            'cohorts': {name: {'queries': len(indices), 'metrics': summarize(indices)} for name, indices in cohort.items()},
            'coverage': {'relevant_authors': relevant_count, 'relevant_with_history': retrievable_count,
                         'queries_with_history': available_queries,
                         'hybrid_candidate_recall_all_authors': candidate_hits / max(1, relevant_count),
                         'hybrid_candidate_recall_known_authors': candidate_hits / max(1, retrievable_count)},
            'learned_vs_baseline': differences, 'failure_analyses': list(failures.values()),
            'mrr_scope': f'Untruncated within each method\'s returned list, up to {engine.candidate_limit} authors.',
            'ablation_scope': 'Feature ablations retrain on identical labels and share hybrid candidates and the hybrid prior. Without-dense removes explicit cosine/rank features, not dense retrieval inside that prior. Standalone lexical/dense baselines test retrieval components.'}


def name_counterfactual(engine, model, queries):
    originals = engine.authors
    changed = 0
    for query in queries:
        before = [(item['person_id'], item['score']) for item in search(engine, query.text, model)]
        try:
            engine.authors = {identifier: ('Aisha Rahman' if index % 2 else 'John Smith')
                              for index, identifier in enumerate(sorted(originals))}
            after = [(item['person_id'], item['score']) for item in search(engine, query.text, model)]
        finally:
            engine.authors = originals
        changed += before != after
    return {'queries': len(queries), 'changed_rankings_or_scores': changed,
            'intervention': 'Replace all author display names with alternating name-origin cues, holding evidence and IDs fixed.',
            'limitation': 'Controlled display-name invariance does not establish demographic fairness or remove historical publication bias.'}
