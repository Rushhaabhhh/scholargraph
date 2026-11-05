"""Evidence-preserving graph reads shared by retrieval and future assistant tools."""

from collections import deque


class GraphQueries:
    def __init__(self, database):
        self.database = database

    def profile(self, author_id: int):
        author = self.database.execute('SELECT id,canonical_name FROM authors WHERE id=?', (author_id,)).fetchone()
        if author is None:
            raise ValueError('Unknown author ID')
        papers = [dict(row) for row in self.database.execute('''SELECT p.id paper_id,p.title,p.year,p.venue,p.source
            FROM papers p JOIN paper_authors pa ON pa.paper_id=p.id WHERE pa.author_id=?
            ORDER BY p.year DESC,p.id''', (author_id,))]
        return {'person_id': author_id, 'name': author['canonical_name'], 'publications': papers,
                'name_sources': [row[0] for row in self.database.execute(
                    'SELECT paper_id FROM paper_authors WHERE author_id=? AND observed_name=? ORDER BY paper_id',
                    (author_id, author['canonical_name']))]}

    def profile_by_observation(self, record_id: str):
        match = self.database.execute('SELECT canonical_author_id,score,decision,features_json FROM entity_resolution_matches WHERE noisy_record_id=?',
                                      (record_id,)).fetchone()
        if match is None or match['decision'] != 'matched' or match['canonical_author_id'] is None:
            raise ValueError('Observation has no unambiguous resolved identity')
        profile = self.profile(match['canonical_author_id'])
        profile['resolution'] = {'record_id': record_id, 'score': match['score'], 'features_json': match['features_json']}
        return profile

    def collaborators(self, author_id: int):
        endpoint = f'author:{author_id}'
        neighbors = {}
        for row in self.database.execute('''SELECT e.source_id,e.target_id,p.id paper_id,p.title,p.year,p.venue,p.source
            FROM context_edges e JOIN papers p ON p.id=e.source_record_id
            WHERE e.edge_type='coauthorship' AND (e.source_id=? OR e.target_id=?)
            ORDER BY p.year DESC,p.id''', (endpoint, endpoint)):
            other = row['target_id'] if row['source_id'] == endpoint else row['source_id']
            identifier = int(other.split(':', 1)[1])
            neighbors.setdefault(identifier, []).append({name: row[name] for name in ('paper_id', 'title', 'year', 'venue', 'source')})
        return [{'person_id': identifier, 'evidence': evidence} for identifier, evidence in sorted(neighbors.items())]

    def collaboration_path(self, source: int, target: int, max_hops=4, max_nodes=5000):
        if not 0 <= max_hops <= 6 or max_nodes < 1:
            raise ValueError('Path bounds are invalid')
        for identifier in (source, target):
            if self.database.execute('SELECT 1 FROM authors WHERE id=?', (identifier,)).fetchone() is None:
                raise ValueError('Unknown author ID')
        if source == target:
            return {'person_ids': [source], 'edges': [], 'truncated': False}
        queue, visited = deque([(source, [source], [])]), {source}
        while queue:
            current, path, edges = queue.popleft()
            if len(edges) >= max_hops:
                continue
            for neighbor in self.collaborators(current):
                identifier = neighbor['person_id']
                if identifier in visited:
                    continue
                edge = {'from': current, 'to': identifier, 'type': 'coauthorship', 'evidence': neighbor['evidence'][:1]}
                if identifier == target:
                    return {'person_ids': path + [identifier], 'edges': edges + [edge], 'truncated': False}
                if len(visited) >= max_nodes:
                    return {'person_ids': [], 'edges': [], 'truncated': True}
                visited.add(identifier)
                queue.append((identifier, path + [identifier], edges + [edge]))
        return {'person_ids': [], 'edges': [], 'truncated': False}
