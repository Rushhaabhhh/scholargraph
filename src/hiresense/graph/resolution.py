"""Conservative linkage of noisy observations to historical DBLP identities.

Ground truth is deliberately absent from this module. Candidate IDs are persisted
so an evaluator can measure blocking recall independently of matching decisions.
"""

import json
import math
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from time import monotonic

_SUFFIX = re.compile(r'\s+\d{4,}$')


def normalize_name(value: str) -> str:
    value = _SUFFIX.sub('', value)
    value = unicodedata.normalize('NFKD', value).casefold()
    return ' '.join(''.join(char if char.isalnum() else ' ' for char in value
                            if not unicodedata.combining(char)).split())


def name_similarity(left: str, right: str) -> float:
    left, right = normalize_name(left).split(), normalize_name(right).split()
    if not left or not right:
        return 0.0
    available = list(right)
    scores = []
    for token in sorted(left, key=lambda item: (-len(item), item)):
        if not available:
            scores.append(0.0)
            continue
        def similarity(other):
            if token == other:
                return 1.0
            if min(len(token), len(other)) == 1:
                return 0.82 if token[0] == other[0] else 0.0
            return SequenceMatcher(None, token, other, autojunk=False).ratio()
        score, index = max((similarity(other), -index) for index, other in enumerate(available))
        available.pop(-index)
        scores.append(score)
    return sum(scores) / max(len(left), len(right))


def _deletions(token):
    return {token[:i] + token[i + 1:] for i in range(len(token))} if len(token) >= 4 else set()


class AuthorMatcher:
    def __init__(self, database, max_candidates: int = 128, max_block_size: int = 2000, year_mode: str = 'exact',
                 policy: str = 'legacy', initial_blocks: bool = True):
        if max_candidates < 1 or max_block_size < 1:
            raise ValueError('Candidate and block limits must be positive')
        if year_mode not in ('exact', 'distance'):
            raise ValueError('Unknown year matching mode')
        if policy not in ('legacy', 'conservative', 'strict'):
            raise ValueError('Unknown identity decision policy')
        self.policy = policy
        self.initial_blocks = initial_blocks
        self.year_mode = year_mode
        self.max_candidates, self.max_block_size = max_candidates, max_block_size
        self.profiles = {}
        self.names, self.tokens, self.deletions = defaultdict(set), defaultdict(set), defaultdict(set)
        self.coauthor_index = defaultdict(set)
        self.surname_initials = defaultdict(set)
        for row in database.execute('SELECT id,canonical_name FROM authors ORDER BY id'):
            identifier, name = row['id'], normalize_name(row['canonical_name'])
            self.profiles[identifier] = {'name': name, 'years': set(), 'venues': set(), 'coauthors': set()}
            self.names[' '.join(sorted(name.split()))].add(identifier)
            parts = name.split()
            if len(parts) > 1:
                self.surname_initials[(parts[-1], parts[0][0])].add(identifier)
            for token in set(name.split()):
                if len(token) > 1:
                    self.tokens[token].add(identifier)
                    for key in _deletions(token):
                        self.deletions[key].add(identifier)
        current, authors, year, venue = None, [], None, None
        def add_context():
            for author in authors:
                profile = self.profiles[author]
                if year is not None:
                    profile['years'].add(year)
                if venue:
                    profile['venues'].add(venue.casefold())
                for other in authors:
                    if author != other:
                        name = self.profiles[other]['name']
                        profile['coauthors'].add(name)
                        self.coauthor_index[name].add(author)
        for row in database.execute('''SELECT pa.paper_id,pa.author_id,p.year,p.venue
                FROM paper_authors pa JOIN papers p ON p.id=pa.paper_id ORDER BY pa.paper_id,pa.author_position'''):
            if row['paper_id'] != current:
                add_context()
                current, authors, year, venue = row['paper_id'], [], row['year'], row['venue']
            authors.append(row['author_id'])
        add_context()

    def candidates(self, record):
        weights = defaultdict(float)
        skipped_blocks = 0
        def add(block, strength):
            nonlocal skipped_blocks
            if len(block) > self.max_block_size:
                skipped_blocks += 1
                return
            weight = strength / max(1.0, math.log2(2 + len(block)))
            for identifier in block:
                weights[identifier] += weight
        name = normalize_name(record['noisy_name'])
        add(self.names.get(' '.join(sorted(name.split())), ()), 12.0)
        if self.initial_blocks:
            parts = name.split()
            for surname in parts:
                if len(surname) > 1:
                    for initial in {p[0] for p in parts if p != surname}:
                        add(self.surname_initials.get((surname, initial), ()), 5.0)
        for token in set(name.split()):
            if len(token) <= 1:
                continue
            add(self.tokens.get(token, ()), 3.0)
            add(self.deletions.get(token, ()), 2.0)
            for key in _deletions(token):
                add(self.tokens.get(key, ()), 2.0)
                add(self.deletions.get(key, ()), 1.0)
        for coauthor in sorted(set(record.get('observed_coauthors', ())))[:20]:
            add(self.coauthor_index.get(normalize_name(coauthor), ()), 2.5)
        ranked = sorted(weights, key=lambda identifier: (-weights[identifier], identifier))
        return ranked[:self.max_candidates], len(ranked), skipped_blocks

    def features(self, record, identifier):
        profile = self.profiles[identifier]
        observed_coauthors = {normalize_name(name) for name in record.get('observed_coauthors', ())}
        observed_years = set(record.get('observed_years', ()))
        observed_venues = {name.casefold() for name in record.get('observed_venues', ())}
        if self.year_mode == 'distance':
            year_score = (sum(max((math.exp(-abs(year - reference) / 5) for reference in profile['years']),
                                  default=0.0) for year in observed_years) / max(1, len(observed_years)))
        else:
            year_score = len(observed_years & profile['years']) / max(1, len(observed_years))
        return {
            'name': name_similarity(record['noisy_name'], profile['name']),
            'coauthors': len(observed_coauthors & profile['coauthors']) / max(1, len(observed_coauthors)),
            'shared_coauthor_count': len(observed_coauthors & profile['coauthors']),
            'venues': len(observed_venues & profile['venues']) / max(1, len(observed_venues)),
            'years': year_score,
        }

    def match(self, record, threshold=0.72, ambiguity_margin=0.06):
        candidates, available, skipped = self.candidates(record)
        scored = []
        for identifier in candidates:
            features = self.features(record, identifier)
            score = sum(features[name] * weight for name, weight in
                        (('name', 0.55), ('coauthors', 0.25), ('venues', 0.12), ('years', 0.08)))
            supported = (features['coauthors'] > 0 or
                         (features['venues'] > 0 and features['years'] > 0 and features['name'] >= 0.93))
            if self.policy == 'conservative':
                # Temporal plausibility alone cannot establish identity. Require
                # independent collaborator evidence, particularly for initials.
                supported = (features['name'] >= 0.85 and features['coauthors'] > 0
                             and (features['shared_coauthor_count'] >= 2 or
                                  (features['name'] >= 0.95 and features['venues'] > 0)))
            elif self.policy == 'strict':
                supported = (features['name'] >= 0.93 and features['shared_coauthor_count'] >= 2
                             and features['coauthors'] >= 0.5 and features['venues'] > 0)
            scored.append((score, identifier, features, supported))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if not scored:
            return None, 0.0, 'unresolved', {}, candidates, available, skipped
        score, identifier, features, supported = scored[0]
        margin = score - scored[1][0] if len(scored) > 1 else score
        effective_threshold = max(threshold, 0.78) if self.policy == 'strict' else threshold
        effective_margin = max(ambiguity_margin, 0.12) if self.policy == 'strict' else ambiguity_margin
        if supported and features['name'] >= 0.7 and score >= effective_threshold:
            decision = 'matched' if margin >= effective_margin else 'ambiguous'
        else:
            decision = 'unresolved'
        return identifier if decision == 'matched' else None, score, decision, dict(features, margin=margin), candidates, available, skipped


def resolve_records(database, noisy_path: str | Path, threshold: float = 0.72,
                    ambiguity_margin: float = 0.06, max_candidates: int = 128,
                    year_mode: str = 'exact', policy: str = 'legacy') -> dict:
    if not 0 <= threshold <= 1 or not 0 <= ambiguity_margin <= 1:
        raise ValueError('Threshold and ambiguity margin must be in [0,1]')
    started = monotonic()
    matcher = AuthorMatcher(database, max_candidates, year_mode=year_mode, policy=policy)
    counts = {'records': 0, 'matched': 0, 'ambiguous': 0, 'unresolved': 0, 'emitted_candidates': 0,
              'candidate_cap_hits': 0, 'oversized_blocks_skipped': 0}
    with database:
        database.execute('DELETE FROM entity_resolution_candidates')
        database.execute('DELETE FROM entity_resolution_matches')
        seen = set()
        with Path(noisy_path).open(encoding='utf-8') as stream:
            for line in stream:
                record = json.loads(line)
                if record['record_id'] in seen or not isinstance(record.get('noisy_name'), str):
                    raise ValueError('Duplicate observation ID or invalid noisy name')
                seen.add(record['record_id'])
                identifier, score, decision, features, candidates, available, skipped = matcher.match(record, threshold, ambiguity_margin)
                database.execute('INSERT INTO entity_resolution_matches VALUES(?,?,?,?,?)',
                                 (record['record_id'], identifier, score, decision, json.dumps(features, sort_keys=True)))
                database.execute('INSERT INTO entity_resolution_candidates VALUES(?,?)',
                                 (record['record_id'], json.dumps(candidates)))
                counts['records'] += 1
                counts[decision] += 1
                counts['emitted_candidates'] += len(candidates)
                counts['candidate_cap_hits'] += available > max_candidates
                counts['oversized_blocks_skipped'] += skipped
    counts['average_candidates'] = counts['emitted_candidates'] / max(1, counts['records'])
    counts['elapsed_seconds'] = round(monotonic() - started, 3)
    counts['policy'] = {'threshold': threshold, 'ambiguity_margin': ambiguity_margin, 'max_candidates': max_candidates,
                        'year_mode': year_mode, 'decision_policy': policy,
                        'false_merge_cost': 'Higher than a false split: merging contaminates expertise and evidence. Abstain on ambiguity.',
                        'blocking': 'Exact unordered name, surname/first-initial, token/deletion signatures, and coauthor inverted indexes; cap candidates and skip oversized blocks.'}
    return counts
