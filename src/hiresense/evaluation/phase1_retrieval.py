"""Bounded, experimental paper-to-author aggregation for retrieval diagnostics.

These methods do not change serving or use relevance labels to generate candidates.
"""
import math
from collections import defaultdict

import numpy as np

from ..retrieval.index import tokens


def paper_ranks(context, paper_limit):
    similarity = context['similarities']
    count = min(paper_limit, len(similarity))
    selected = np.argpartition(-similarity, count - 1)[:count] if count else []
    dense = sorted(selected, key=lambda i: (-float(similarity[i]), int(i)))
    lexical = list(context['lexical_scores'])
    scores, strong = defaultdict(float), set()
    for paper_list in (lexical, dense):
        for rank, paper in enumerate(paper_list, 1):
            scores[int(paper)] += 1 / (60 + rank)
            if rank <= 100:
                strong.add(int(paper))
    return scores, strong


def aggregate_papers(index, context, mode):
    """Rank all authors reached by the source pool, before the author cap."""
    scores, strong = paper_ranks(context, index.paper_limit)
    author_scores = defaultdict(list)
    for paper, score in scores.items():
        for author in index.paper_authors[paper]:
            author_scores[author].append((score, paper))
    values = {}
    for author, papers in author_scores.items():
        papers.sort(key=lambda row: (-row[0], row[1]))
        values3 = [item[0] for item in papers[:3]]
        if mode == 'max':
            value = values3[0]
        elif mode == 'top3':
            value = sum(score * weight for score, weight in zip(values3, (1.0, .6, .36)))
        elif mode == 'coverage':
            qualifying = [p for _, p in papers if p in strong]
            recent = max((index.papers[p]['year'] or 0 for p in qualifying), default=0)
            age = math.exp(-max(0, index.anchor_year - recent) / 5) if recent else 0.0
            fraction = len(qualifying) / max(1, len(index.author_papers[author]))
            value = values3[0] + .3 * sum(values3) / len(values3) + .002 * min(len(qualifying), 3) + .002 * fraction + .002 * age
        else:
            raise ValueError('Unknown aggregation mode')
        values[author] = value
    return sorted(values, key=lambda author: (-values[author], author))


def fuse_author_ranks(paper_authors, profiles, *, profile_weight=.25):
    """Fuse independent author-topic and paper-author routes at author level."""
    values = defaultdict(float)
    for rank, author in enumerate(paper_authors, 1):
        values[author] += 1 / (60 + rank)
    for rank, author in enumerate(profiles, 1):
        values[author] += profile_weight / (60 + rank)
    return sorted(values, key=lambda author: (-values[author], author))


def topical_neighbors(index, context, query, seeds, *, seed_limit=32, edge_limit=128, minimum_similarity=.4):
    """Expand only through dated, query-matching shared publication evidence."""
    candidates = defaultdict(list)
    query_terms = tokens(query)
    for author in seeds[:seed_limit]:
        papers = sorted(index.author_papers[author], key=lambda p: (-float(context['similarities'][p]), p))[:3]
        for paper in papers:
            score = float(context['similarities'][paper])
            if (score < minimum_similarity or not query_terms.intersection(index.title_tokens[paper])
                    or not index.papers[paper]['year'] or index.papers[paper]['year'] > index.anchor_year):
                continue
            for other in index.paper_authors[paper]:
                if other != author:
                    candidates[other].append((score, author, paper))
    ordered = sorted(candidates, key=lambda author: (-max(x[0] for x in candidates[author]), author))
    output = []
    for other in ordered:
        for _, seed, paper in sorted(candidates[other], reverse=True):
            left, right = sorted((seed, other))
            edge = index.database.execute('''SELECT 1 FROM context_edges WHERE source_id=? AND target_id=?
                AND edge_type='coauthorship' AND source_record_id=? AND edge_year=? LIMIT 1''',
                (f'author:{left}', f'author:{right}', index.papers[paper]['id'], index.papers[paper]['year'])).fetchone()
            if edge:
                output.append(other)
                break
        if len(output) == edge_limit:
            break
    return output
