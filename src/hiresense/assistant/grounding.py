"""Verify typed factual claims against source relations and canonical rendering.

Checking citations alone is insufficient: supplied wording, people and years must
also agree. This verifier covers constrained facts, not arbitrary prose entailment.
"""

import json
from pydantic import ValidationError

from ..retrieval.index import tokens
from .schemas import ClaimDraft
from .safety import data_warnings


def claim_text(kind, paper, collaborator_id=None, term=None):
    title = json.dumps(paper['title'], ensure_ascii=False)
    date = str(paper['year']) if paper['year'] is not None else 'year unavailable'
    if kind == 'authorship':
        return f'Authored {title} ({date}).'
    if kind == 'coauthorship':
        return f'Coauthored {title} ({date}) with person {collaborator_id}.'
    return f'The title of {title} ({date}) contains the term {json.dumps(term, ensure_ascii=False)}.'


class GroundingVerifier:
    def __init__(self, database):
        self.database = database

    def verify(self, draft):
        raw = draft.model_dump() if isinstance(draft, ClaimDraft) else dict(draft)
        result = {**raw, 'supported': False, 'reason': None, 'sources': []}
        try:
            claim = ClaimDraft.model_validate(raw)
        except (ValidationError, TypeError, ValueError):
            return dict(result, reason='invalid_claim_schema')
        paper = self.database.execute('SELECT id,title,year,source FROM papers WHERE id=?', (claim.paper_id,)).fetchone()
        if paper is None or paper['source'] != 'dblp':
            return dict(result, reason='missing_source_paper')
        authored = self.database.execute('SELECT 1 FROM paper_authors WHERE paper_id=? AND author_id=?',
                                         (claim.paper_id, claim.person_id)).fetchone()
        if authored is None:
            return dict(result, reason='unsupported_authorship')
        if claim.year != paper['year']:
            return dict(result, reason='incorrect_year')
        edge_id = None
        if claim.kind == 'coauthorship':
            if claim.term is not None:
                return dict(result, reason='unexpected_claim_arguments')
            if claim.collaborator_id is None or claim.collaborator_id == claim.person_id:
                return dict(result, reason='invalid_collaborator')
            left, right = sorted((claim.person_id, claim.collaborator_id))
            edge = self.database.execute('''SELECT edge_id FROM context_edges WHERE edge_type='coauthorship'
                AND source_id=? AND target_id=? AND source_record_id=? AND edge_year IS ?''',
                (f'author:{left}', f'author:{right}', claim.paper_id, claim.year)).fetchone()
            if edge is None:
                return dict(result, reason='missing_collaboration_edge')
            edge_id = edge['edge_id']
        elif claim.kind == 'title_term':
            if claim.collaborator_id is not None:
                return dict(result, reason='unexpected_claim_arguments')
            if claim.term is None or claim.term not in tokens(paper['title']):
                return dict(result, reason='unsupported_title_term')
        elif claim.collaborator_id is not None or claim.term is not None:
            return dict(result, reason='unexpected_claim_arguments')
        expected = claim_text(claim.kind, paper, claim.collaborator_id, claim.term)
        if claim.text != expected:
            return dict(result, reason='wording_not_supported_by_fact')
        source = {'paper_id': paper['id'], 'year': paper['year'], 'source': paper['source']}
        if edge_id:
            source['edge_id'] = edge_id
        return dict(result, supported=True, reason=None, sources=[source], data_warnings=data_warnings(paper['title']))

    def authorship(self, person_id, paper_id):
        paper = self.database.execute('SELECT id,title,year FROM papers WHERE id=?', (paper_id,)).fetchone()
        if paper is None:
            return self.verify({'kind': 'authorship', 'person_id': person_id, 'paper_id': paper_id, 'year': None,
                                'text': 'Unverified publication claim.'})
        return self.verify({'kind': 'authorship', 'person_id': person_id, 'paper_id': paper_id,
                            'year': paper['year'], 'text': claim_text('authorship', paper)})

    def explain(self, results):
        output = []
        for result in results:
            claims = [self.authorship(result['person_id'], paper['paper_id']) for paper in result['evidence'][:2]]
            explanation = ' '.join(claim['text'] for claim in claims if claim['supported']) or 'No verified publication claim is available.'
            output.append(dict(result, claims=claims, explanation=explanation,
                               grounding={'claims': len(claims), 'unsupported': sum(not claim['supported'] for claim in claims)}))
        return output
