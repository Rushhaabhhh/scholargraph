"""Evaluate linkage against later authorships without exposing their papers to profiles."""

import random
from collections import Counter
from time import monotonic

from ..data.noise import corrupt_name, visible_name
from ..graph.resolution import AuthorMatcher
from .split import assert_no_leakage, dataset_digest


def evaluate_temporal_identity(source, graph, start_year, end_year, *, rate=1.0, seed=42,
                               threshold=0.72, ambiguity_margin=0.06, max_candidates=128):
    """Compare matchers on the same later records, including unseen identities.

    The source supplies observations and evaluator-only truth; the matcher sees only
    historical graph profiles and the observed noisy name, coauthors, venue and year.
    """
    cutoff_row = graph.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if cutoff_row is None:
        raise ValueError('A historical graph snapshot with a cutoff is required')
    cutoff = int(cutoff_row[0])
    if not cutoff < start_year <= end_year <= 9999 or not 0 < rate <= 1:
        raise ValueError('Require cutoff < start year <= end year and a sampling rate in (0, 1]')
    assert_no_leakage(graph, [], [], cutoff)
    origin = graph.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
    if origin is None or origin[0] != dataset_digest(source):
        raise ValueError('Source database does not match the graph snapshot provenance')
    started = monotonic()
    matcher = AuthorMatcher(graph, max_candidates=max_candidates)
    strategies = {'exact': ('exact', 'legacy'), 'distance': ('distance', 'legacy'),
                  'conservative': ('distance', 'conservative'), 'strict': ('distance', 'strict')}
    known_ids = set(matcher.profiles)
    strategies['conservative_without_initial_block'] = ('distance', 'conservative')
    counts = {mode: Counter() for mode in strategies}
    by_corruption = {mode: {kind: Counter() for kind in ('initials','name_order','typo','transliteration')} for mode in strategies}
    corruptions = Counter()
    rng = random.Random(seed)
    for paper in source.execute('SELECT id,year,venue FROM papers WHERE year BETWEEN ? AND ? ORDER BY id',
                                (start_year, end_year)):
        authors = source.execute('SELECT author_id, observed_name FROM paper_authors WHERE paper_id=? ORDER BY author_position',
                                 (paper['id'],)).fetchall()
        for author in authors:
            if rng.random() >= rate:
                continue
            kind = rng.choice(('initials', 'name_order', 'typo', 'transliteration'))
            record = {'noisy_name': corrupt_name(author['observed_name'], kind, rng),
                      'observed_years': [paper['year']],
                      'observed_venues': [paper['venue']] if paper['venue'] else [],
                      'observed_coauthors': [visible_name(other['observed_name']) for other in authors
                                             if other['author_id'] != author['author_id'] and rng.random() >= 0.15]}
            truth = author['author_id']
            known = truth in known_ids
            corruptions[kind] += 1
            for mode, (year_mode, policy) in strategies.items():
                matcher.year_mode, matcher.policy = year_mode, policy
                matcher.initial_blocks = mode != 'conservative_without_initial_block'
                identifier, _, decision, _, candidates, _, _ = matcher.match(record, threshold, ambiguity_margin)
                c = counts[mode]
                c['observations'] += 1
                c['known' if known else 'unseen'] += 1
                c['known_candidate_hits'] += known and truth in candidates
                c['matched'] += identifier is not None
                c['correct_known_matches'] += known and identifier == truth
                c['incorrect_merges'] += identifier is not None and identifier != truth
                c['incorrect_merges_unseen'] += not known and identifier is not None
                c['known_abstentions'] += known and identifier is None
                c['unseen_abstentions'] += not known and identifier is None
                c['ambiguous'] += decision == 'ambiguous'
                subgroup = by_corruption[mode][kind]
                subgroup['observations'] += 1
                subgroup['known'] += known
                subgroup['candidate_hits'] += known and truth in candidates
                subgroup['assigned'] += identifier is not None
                subgroup['correct'] += known and identifier == truth
                subgroup['incorrect_merges'] += identifier is not None and identifier != truth
    def wilson(successes, total):
        if not total: return None
        z = 1.959963984540054
        p = successes / total
        center = (p + z*z/(2*total)) / (1 + z*z/total)
        half = z*((p*(1-p)/total + z*z/(4*total*total))**.5) / (1 + z*z/total)
        return [max(0.,center-half),min(1.,center+half)]
    results = {}
    for mode, c in counts.items():
        ratio = lambda numerator, denominator: numerator / denominator if denominator else None
        results[mode] = {**c, 'precision': ratio(c['correct_known_matches'], c['matched']),
                         'known_recall': ratio(c['correct_known_matches'], c['known']),
                         'known_candidate_recall': ratio(c['known_candidate_hits'], c['known']),
                         'unseen_false_merge_rate': ratio(c['incorrect_merges_unseen'], c['unseen']),
                         'precision_wilson_95pct': wilson(c['correct_known_matches'], c['matched']),
                         'known_recall_wilson_95pct': wilson(c['correct_known_matches'], c['known']),
                         'by_corruption': {k: dict(v) for k,v in by_corruption[mode].items()}}
    return {'protocol': 'Later authorship observations matched only against pre-cutoff profiles; unseen identities included.',
            'limitation': 'Synthetic name noise; known-reference linkage with unknown-identity rejection, not open-world clustering. Wilson intervals treat observations as independent; repeated authors can be dependent.',
            'cutoff_year': cutoff, 'start_year': start_year, 'end_year': end_year, 'seed': seed, 'sample_rate': rate,
            'threshold': threshold, 'ambiguity_margin': ambiguity_margin, 'max_candidates': max_candidates,
            'year_modes': {'exact': 'Exact year overlap.', 'distance': 'Exponential decay with distance to nearest historical year.',
                           'conservative': 'Year distance with strong name and independent collaborator evidence; abstain otherwise.',
                           'conservative_without_initial_block': 'Same conservative matcher without the surname/first-initial candidate channel.',
                           'strict': 'At least two coauthors, >=50% collaborator overlap, name>=0.93, venue match, score>=0.78 and margin>=0.12.'},
            'corruptions': dict(corruptions), 'results': results, 'elapsed_seconds': round(monotonic() - started, 3)}
