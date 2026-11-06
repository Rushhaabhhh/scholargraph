"""Ranking metrics with explicit cutoffs and untruncated reciprocal rank."""

import math


def ranking_metrics(ranked_ids: list[int], relevant_ids: set[int], k: int = 10) -> dict[str, float]:
    if k < 1:
        raise ValueError('Ranking cutoff must be positive')
    if len(ranked_ids) != len(set(ranked_ids)):
        raise ValueError('Ranked author IDs must be unique')
    dcg = sum(1 / math.log2(index + 2) for index, identifier in enumerate(ranked_ids[:k]) if identifier in relevant_ids)
    ideal = sum(1 / math.log2(index + 2) for index in range(min(k, len(relevant_ids))))
    first = next((index + 1 for index, identifier in enumerate(ranked_ids) if identifier in relevant_ids), 0)
    return {f'ndcg_at_{k}': dcg / ideal if ideal else 0.0,
            'mrr': 1 / first if first else 0.0,
            f'mrr_at_{k}': 1 / first if first and first <= k else 0.0,
            f'hit_at_{k}': float(bool(first and first <= k))}
