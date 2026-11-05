"""Train an evidence-feature reranker and export its trees as portable JSON."""

import math
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from ..data.artifacts import write_json
from ..evaluation.metrics import ranking_metrics
from ..retrieval.index import FEATURE_NAMES


def raw_tree_scores(features, model):
    features = np.asarray(features, dtype=np.float32)
    schema = FEATURE_NAMES
    if model['version'] == 'evidence-lambdamart-v2':
        from ..retrieval.evidence import EVIDENCE_FEATURES
        schema = EVIDENCE_FEATURES
    elif model['version'] == 'hybrid-lambdamart-v1':
        from ..retrieval.hybrid import HYBRID_FEATURES
        schema = HYBRID_FEATURES
    if tuple(model['features']) != schema or features.ndim != 2 or features.shape[1] != len(schema):
        raise ValueError('Reranker feature schema differs')
    selected = features[:, model['selected_features']]
    values = np.full(len(features), model['initial_log_odds'], dtype=np.float64)
    for tree in model['trees']:
        left, right = np.asarray(tree['left']), np.asarray(tree['right'])
        indices = np.zeros(len(features), dtype=np.int32)
        tree_feature, threshold = np.asarray(tree['feature']), np.asarray(tree['threshold'])
        active = left[indices] != -1
        while active.any():
            rows = np.flatnonzero(active)
            nodes = indices[rows]
            go_left = selected[rows, tree_feature[nodes]] <= threshold[nodes]
            indices[rows] = np.where(go_left, left[nodes], right[nodes])
            active = left[indices] != -1
        values += model['learning_rate'] * np.asarray(tree['value'])[indices]
    return values


def score_model(features, model):
    if model.get('retrieval_kind') in ('hybrid', 'evidence') and model['version'] == 'gradient-boosted-expert-v1':
        features = np.asarray(features)[:, :len(FEATURE_NAMES)]
    raw = raw_tree_scores(features, model)
    if 'blend_alpha' not in model:
        return raw
    probability = 1 / (1 + np.exp(-np.clip(raw, -40, 40)))
    prior = np.asarray(features)[:, FEATURE_NAMES.index('hybrid_rrf')]
    alpha = model['blend_alpha']
    return alpha * probability + (1 - alpha) * prior


def _export(classifier, selected_features, metadata):
    probability = float(classifier.init_.predict_proba(np.zeros((1, len(selected_features))))[0, 1])
    trees = []
    for estimator in classifier.estimators_[:, 0]:
        tree = estimator.tree_
        trees.append({'left': tree.children_left.tolist(), 'right': tree.children_right.tolist(),
                      'feature': tree.feature.tolist(), 'threshold': tree.threshold.tolist(),
                      'value': tree.value[:, 0, 0].tolist()})
    return {'version': 'gradient-boosted-expert-v1', 'features': list(FEATURE_NAMES), 'selected_features': selected_features,
            'initial_log_odds': math.log(probability / (1 - probability)), 'learning_rate': classifier.learning_rate,
            'trees': trees, **metadata}


def cache_metrics(cache, scores):
    values = []
    for index, query in enumerate(cache['queries']):
        start, end = cache['offsets'][index:index + 2]
        ids = cache['author_ids'][start:end]
        order = np.lexsort((ids, -scores[start:end]))
        values.append(ranking_metrics(ids[order].tolist(), set(query.relevant_author_ids)))
    return {key: float(np.mean([item[key] for item in values])) if values else 0.0 for key in ('ndcg_at_10', 'mrr')}


def train_ranker(train_cache, validation_cache, output_path: str | Path, metadata: dict,
                 seed=42, selected_features=None, parameters=None, hard_negatives=24, tail_negatives=8):
    from sklearn.ensemble import GradientBoostingClassifier

    selected_features = list(range(len(FEATURE_NAMES))) if selected_features is None else list(selected_features)
    rng = np.random.default_rng(seed)
    rows, labels, weights = [], [], []
    used_queries = 0
    for index, query in enumerate(train_cache['queries']):
        start, end = train_cache['offsets'][index:index + 2]
        relevant = set(query.relevant_author_ids)
        positives = [row for row in range(start, end) if int(train_cache['author_ids'][row]) in relevant]
        negatives = [row for row in range(start, end) if int(train_cache['author_ids'][row]) not in relevant]
        if not positives or not negatives:
            continue
        # Hard negatives come from retrieval; sample tail negatives as additional contrast.
        hard = negatives[:hard_negatives]
        tail = negatives[hard_negatives:]
        if tail:
            hard.extend(rng.choice(tail, min(tail_negatives, len(tail)), replace=False).tolist())
        rows.extend(positives + hard)
        labels.extend([1] * len(positives) + [0] * len(hard))
        weights.extend([0.5 / len(positives)] * len(positives) + [0.5 / len(hard)] * len(hard))
        used_queries += 1
    if not used_queries:
        raise ValueError('No training queries have both retrieved relevant authors and contrast candidates')
    x = train_cache['features'][rows][:, selected_features]
    y, sample_weight = np.asarray(labels), np.asarray(weights)
    settings = [parameters] if parameters else [dict(n_estimators=40, max_depth=2), dict(n_estimators=80, max_depth=2), dict(n_estimators=80, max_depth=3)]
    candidates = []
    with threadpool_limits(limits=2):
        for setting in settings:
            classifier = GradientBoostingClassifier(**setting, learning_rate=0.06, min_samples_leaf=10,
                                                    random_state=seed, loss='log_loss')
            classifier.fit(x, y, sample_weight=sample_weight)
            model = _export(classifier, selected_features, metadata)
            expected = classifier.decision_function(validation_cache['features'][:, selected_features])
            actual = raw_tree_scores(validation_cache['features'], model)
            if not np.allclose(expected, actual, atol=1e-8):
                raise ValueError('Portable tree inference does not match the trained estimator')
            blends = []
            for alpha in (0.0, 0.01, 0.025, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0):
                model['blend_alpha'] = alpha
                metrics = cache_metrics(validation_cache, score_model(validation_cache['features'], model))
                blends.append((metrics['ndcg_at_10'], metrics['mrr'], alpha, metrics))
            blend = max(blends, key=lambda item: (item[0], item[1]))
            model['blend_alpha'] = blend[2]
            metrics = blend[3]
            candidates.append((metrics['ndcg_at_10'], metrics['mrr'], setting, model, metrics))
    best = max(candidates, key=lambda item: (item[0], item[1]))
    model = best[3]
    model['parameters'] = best[2]
    model['training'] = {'seed': seed, 'examples': len(rows), 'positive_examples': int(y.sum()),
                         'queries_used': used_queries, 'queries_without_training_contrast': len(train_cache['queries']) - used_queries,
                         'label_policy': 'Future authors are positive; retrieved non-authors are sampled unjudged negatives. Per-query and class-balanced weights.',
                         'selection': 'Choose tree parameters and hybrid/learned blend by validation nDCG@10, then MRR; no test labels are read.',
                         'negative_sampling': {'hard': hard_negatives, 'tail': tail_negatives},
                         'blend_grid': [0.0, 0.01, 0.025, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0]}
    model['validation_candidates'] = [{'parameters': item[2], 'blend_alpha': item[3]['blend_alpha'], 'metrics': item[4]} for item in candidates]
    write_json(output_path, model)
    return {'examples': len(rows), 'queries_used': used_queries, 'parameters': best[2], 'validation': best[4],
            'blend_alpha': model['blend_alpha'], 'selected_features': [FEATURE_NAMES[index] for index in selected_features]}
