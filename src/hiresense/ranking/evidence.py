"""Experimental query-dependent author evidence; not used by the serving model.

Every feature uses only the author's eligible historical papers. Relevance
thresholds are uncalibrated retrieval heuristics, not human judgements.
"""
import math

from ..retrieval.index import tokens

EVIDENCE_FEATURES = (
    'bm25_top3_weighted', 'dense_top3_weighted', 'combined_top3_weighted',
    'strong_papers_log', 'strong_concentration_smoothed', 'recent_strong_log',
    'strong_most_recent_decay', 'topical_recency_weighted', 'publication_count_log_capped',
)


def eligible_lexical_max(index, context):
    minimum_year = context.get('since_year')
    return max((score for paper, score in context['lexical_scores'].items()
                if index.papers[paper]['year'] is not None
                and index.papers[paper]['year'] <= index.anchor_year
                and (minimum_year is None or index.papers[paper]['year'] >= minimum_year)), default=0.0)


def evidence_features(index, context, author, query, *, strong_similarity=.4, recent_years=5, lexical_max=None):
    """Return bounded publication features with no future or cross-author evidence.

    A strong paper has title-token overlap and cosine similarity >= the specified
    heuristic. Its strength is not a calibrated probability or relevance label.
    """
    query_terms = tokens(query)
    minimum_year = context.get('since_year')
    eligible = [p for p in index.author_papers.get(author, ())
                if index.papers[p]['year'] is not None
                and index.papers[p]['year'] <= index.anchor_year
                and (minimum_year is None or index.papers[p]['year'] >= minimum_year)]
    if not eligible:
        return [0.0] * len(EVIDENCE_FEATURES)
    lexical = context['lexical_scores']
    lexical_max = eligible_lexical_max(index, context) if lexical_max is None else lexical_max
    similarities = context['similarities']
    bm25 = sorted((max(0.0, float(lexical.get(p, 0.0))) / max(lexical_max, 1e-9) for p in eligible), reverse=True)
    dense = sorted((max(0.0, float(similarities[p])) for p in eligible), reverse=True)
    combined = sorted((max(0.0, float(lexical.get(p, 0.0))) / max(lexical_max, 1e-9)
                       + max(0.0, float(similarities[p])) for p in eligible), reverse=True)
    strong = [p for p in eligible if float(similarities[p]) >= strong_similarity
              and query_terms.intersection(index.title_tokens[p])]
    decay = lambda p: math.exp(-max(0, index.anchor_year - index.papers[p]['year']) / 5)
    weighted = lambda values: sum(v*w for v,w in zip(values[:3], (1.0,.6,.36)))
    return [weighted(bm25), weighted(dense), weighted(combined), math.log1p(min(len(strong), 20)),
            len(strong) / (len(eligible) + 3),
            math.log1p(min(sum(index.papers[p]['year'] >= index.anchor_year-recent_years+1 for p in strong),20)),
            max((decay(p) for p in strong),default=0.0),
            max((float(similarities[p])*decay(p) for p in strong),default=0.0),
            math.log1p(min(len(eligible),100))]

GRAPH_FEATURES = ('topical_coauthor_strength', 'topical_coauthor_recency', 'topical_collaborator_normalized')


def graph_features(index, context, author, query):
    """Bounded one-hop signals backed by a matching dated coauthorship edge."""
    terms = tokens(query)
    minimum_year = context.get('since_year')
    papers = [p for p in index.author_papers.get(author, ())
              if index.papers[p]['year'] is not None and index.papers[p]['year'] <= index.anchor_year
              and (minimum_year is None or index.papers[p]['year'] >= minimum_year)
              and len(index.paper_authors[p]) > 1 and terms.intersection(index.title_tokens[p])]
    papers.sort(key=lambda p: (-float(context['similarities'][p]), p))
    strengths, recencies, normalized = [], [], []
    for p in papers[:3]:
        paper = index.papers[p]
        edge = index.database.execute('''SELECT source_id,target_id FROM context_edges
            WHERE edge_type='coauthorship' AND source_record_id=? AND edge_year=?
            AND (source_id=? OR target_id=?) LIMIT 1''',
            (paper['id'], paper['year'], f'author:{author}', f'author:{author}')).fetchone()
        if not edge:
            continue
        partner = int((edge['target_id'] if edge['source_id'] == f'author:{author}' else edge['source_id']).split(':')[1])
        if partner not in index.paper_authors[p]:
            continue
        score=max(0.0,float(context['similarities'][p]))
        strengths.append(score)
        recencies.append(score*math.exp(-max(0,index.anchor_year-paper['year'])/5))
        normalized.append(score / math.sqrt(max(1,index.degree[partner])))
    return [max(strengths,default=0.),max(recencies,default=0.),max(normalized,default=0.)]
