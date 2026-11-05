"""Train a query-grouped ranker and export numeric trees for dependency-free serving."""
from time import monotonic

import numpy as np

from ..data.artifacts import write_json
from ..retrieval.hybrid import HYBRID_FEATURES
from .scoring import cache_metrics, raw_tree_scores, score_model


def _tree(root):
    arrays = {name: [] for name in ('left', 'right', 'feature', 'threshold', 'value')}
    def visit(node):
        index = len(arrays['left'])
        for name, value in (('left', -1), ('right', -1), ('feature', -2), ('threshold', 0), ('value', 0)):
            arrays[name].append(value)
        if 'leaf_value' in node:
            arrays['value'][index] = float(node['leaf_value'])
        else:
            if node['decision_type'] != '<=':
                raise ValueError('Portable serving supports numeric finite features only')
            arrays['feature'][index] = node['split_feature']
            arrays['threshold'][index] = float(node['threshold'])
            arrays['left'][index] = visit(node['left_child'])
            arrays['right'][index] = visit(node['right_child'])
        return index
    visit(root)
    return arrays


def training_rows(cache, seed):
    rng = np.random.default_rng(seed)
    rows, labels, groups = [], [], []
    for i, query in enumerate(cache['queries']):
        start, end = cache['offsets'][i:i + 2]
        relevant = set(query.relevant_author_ids)
        positives = [row for row in range(start, end) if int(cache['author_ids'][row]) in relevant]
        negatives = [row for row in range(start, end) if int(cache['author_ids'][row]) not in relevant]
        if not positives or not negatives:
            continue
        contrast = negatives[:48]
        if len(negatives) > 48:
            contrast += rng.choice(negatives[48:], min(16, len(negatives) - 48), replace=False).tolist()
        rows.extend(positives + contrast)
        labels.extend([1] * len(positives) + [0] * len(contrast))
        groups.append(len(positives) + len(contrast))
    if not groups:
        raise ValueError('No training queries have retrieved positives and contrasts')
    return np.asarray(rows), np.asarray(labels), groups


def train_lambdamart(train, validation, output, metadata, *, seed=42, removed=(), settings=None):
    from lightgbm import LGBMRanker
    started = monotonic()
    selected = [i for i, name in enumerate(HYBRID_FEATURES) if name not in removed]
    rows, labels, groups = training_rows(train, seed)
    settings = settings or [dict(n_estimators=80, num_leaves=7), dict(n_estimators=160, num_leaves=7),
                            dict(n_estimators=160, num_leaves=15)]
    trials = []
    x = train['features'][rows][:, selected]
    valid_x = validation['features'][:, selected]
    for setting in settings:
        fitted = LGBMRanker(objective='lambdarank', learning_rate=0.04, min_child_samples=30,
                           reg_lambda=2.0, n_jobs=2, random_state=seed, verbosity=-1,
                           deterministic=True, force_col_wise=True, **setting)
        fitted.fit(x, labels, group=groups)
        model = {'version': 'hybrid-lambdamart-v1',
                 'features': list(HYBRID_FEATURES),
                 'selected_features': selected, 'initial_log_odds': 0.0, 'learning_rate': 1.0,
                 'trees': [_tree(item['tree_structure']) for item in fitted.booster_.dump_model()['tree_info']],
                 'parameters': setting, **metadata}
        if not np.allclose(fitted.predict(valid_x), raw_tree_scores(validation['features'], model), atol=1e-7):
            raise ValueError('Portable ranker predictions differ from the fitted model')
        blends = []
        for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
            model['blend_alpha'] = alpha
            metrics = cache_metrics(validation, score_model(validation['features'], model))
            blends.append((metrics['ndcg_at_10'], metrics['mrr'], alpha, metrics))
        best = max(blends, key=lambda item: (item[0], item[1]))
        model['blend_alpha'] = best[2]
        trials.append((best[0], best[1], model, best[3]))
    chosen = max(trials, key=lambda item: (item[0], item[1]))
    model = chosen[2]
    model['training'] = {'seed': seed, 'examples': len(rows), 'positive_examples': int(labels.sum()),
                         'queries_used': len(groups), 'available_train_queries': len(train['queries']),
                         'objective': 'Query-grouped LambdaRank; negatives are sampled unjudged contrasts.',
                         'selection': 'Tree configuration and hybrid blend selected by validation nDCG@10, then MRR.',
                         'removed_features': list(removed)}
    model['validation_candidates'] = [{'parameters': item[2]['parameters'], 'blend_alpha': item[2]['blend_alpha'],
                                       'metrics': item[3]} for item in trials]
    write_json(output, model)
    return {'examples': len(rows), 'positive_examples': int(labels.sum()), 'queries_used': len(groups),
            'parameters': model['parameters'], 'blend_alpha': model['blend_alpha'], 'validation': chosen[3],
            'removed_features': list(removed), 'elapsed_seconds': round(monotonic() - started, 3)}
