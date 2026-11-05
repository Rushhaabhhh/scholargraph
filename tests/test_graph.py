"""Identity errors, bounded blocking, graph reconstruction, and provenance."""
import json
import tempfile
import unittest
from pathlib import Path

from hiresense.contracts import SplitConfig
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.resolution import evaluate_resolution
from hiresense.evaluation.identity_temporal import evaluate_temporal_identity
from hiresense.evaluation.split import write_split
from hiresense.graph.build import build_context_graph, validate_graph
from hiresense.graph.queries import GraphQueries
from hiresense.graph.resolution import AuthorMatcher, normalize_name, resolve_records

FIXTURE = Path(__file__).parent / 'fixtures/temporal.xml'


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        source = connect(self.path / 'source.sqlite3')
        initialize(source)
        ingest(source, FIXTURE)
        write_split(source, self.path / 'dataset', SplitConfig(2019, 2020, 2021, 2022))
        source.close()
        self.database = connect(self.path / 'dataset/graph.sqlite3')
        initialize(self.database)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_graph_is_typed_dated_sourced_and_idempotent(self):
        first = build_context_graph(self.database)
        second = build_context_graph(self.database)
        self.assertEqual(first['sha256'], second['sha256'])
        self.assertEqual(first['context_edges'], second['context_edges'])
        self.assertEqual(first['coauthorship_edges'], 1)
        rows = self.database.execute('''SELECT e.*,p.year paper_year FROM context_edges e
            JOIN papers p ON p.id=e.source_record_id''').fetchall()
        self.assertEqual(len(rows), first['context_edges'])
        prefixes = {'author_paper': ('author:', 'paper:'), 'author_venue': ('author:', 'venue:'), 'coauthorship': ('author:', 'author:')}
        for row in rows:
            left, right = prefixes[row['edge_type']]
            self.assertTrue(row['source_id'].startswith(left))
            self.assertTrue(row['target_id'].startswith(right))
            self.assertEqual(row['edge_year'], row['paper_year'])
            self.assertLessEqual(row['edge_year'], 2019)
        with self.assertRaises(ValueError):
            build_context_graph(self.database, 2018)

    def test_graph_audit_detects_fabricated_source_relationships(self):
        build_context_graph(self.database)
        self.database.execute("INSERT INTO context_edges VALUES('fabricated','author:1','author:2','coauthorship',2018,'history/graph',1.0)")
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            validate_graph(self.database)

    def test_rebuild_removes_stale_edges_after_relationship_correction(self):
        build_context_graph(self.database)
        author = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0001'").fetchone()[0]
        self.database.execute("DELETE FROM paper_authors WHERE paper_id='history/graph' AND author_id=?", (author,))
        self.database.commit()
        rebuilt = build_context_graph(self.database)
        self.assertEqual(rebuilt['coauthorship_edges'], 0)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM context_edges WHERE source_id=?", (f'author:{author}',)).fetchone()[0], 0)

    def test_names_alone_cannot_merge_and_context_resolves_same_name_identities(self):
        self.assertEqual(normalize_name('Jürgen Müller 0001'), 'jurgen muller')
        first = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0001'").fetchone()[0]
        matcher = AuthorMatcher(self.database)
        record = {'noisy_name': 'A. Kim', 'observed_coauthors': ['Bea Muller'],
                  'observed_venues': ['Graph Journal'], 'observed_years': [2018]}
        match = matcher.match(record)
        self.assertEqual(match[0], first)
        self.assertGreater(match[3]['coauthors'], 0)
        self.assertGreater(match[3]['venues'], 0)
        self.assertGreater(match[3]['years'], 0)
        self.assertIsNone(matcher.match({'noisy_name': 'Alex Kim'})[0])
        self.assertEqual(matcher.candidates({'noisy_name': 'Unrelated Uniquezzzz'})[0], [])

    def test_temporal_identity_evaluates_known_and_new_people_without_future_profiles(self):
        source = connect(self.path / 'source.sqlite3')
        try:
            report = evaluate_temporal_identity(source, self.database, 2020, 2020, seed=42)
            for result in report['results'].values():
                self.assertEqual(result['observations'], 2)
                self.assertEqual(result['known'], 1)
                self.assertEqual(result['unseen'], 1)
                self.assertEqual(result['unseen_abstentions'] + result['incorrect_merges_unseen'], 1)
            self.assertEqual(report, evaluate_temporal_identity(source, self.database, 2020, 2020, seed=42) | {'elapsed_seconds': report['elapsed_seconds']})
            with self.assertRaises(ValueError):
                evaluate_temporal_identity(source, self.database, 2019, 2020)
            source.execute("UPDATE papers SET content_sha256='changed' WHERE id='train/future'")
            with self.assertRaisesRegex(ValueError, 'provenance'):
                evaluate_temporal_identity(source, self.database, 2020, 2020)
        finally:
            source.close()

    def test_ambiguous_initials_abstain_instead_of_incorrect_merge(self):
        a = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0001'").fetchone()[0]
        b = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0002'").fetchone()[0]
        matcher = AuthorMatcher(self.database)
        # Give both identities identical non-name evidence to force a true ambiguity.
        matcher.profiles[b]['years'] = set(matcher.profiles[a]['years'])
        matcher.profiles[b]['venues'] = set(matcher.profiles[a]['venues'])
        record = {'noisy_name': 'Alex Kim', 'observed_venues': ['Graph Journal'], 'observed_years': [2018]}
        result = matcher.match(record)
        self.assertIsNone(result[0])
        self.assertEqual(result[2], 'ambiguous')

    def test_candidate_cap_and_evaluator_detect_incorrect_merge(self):
        matcher = AuthorMatcher(self.database, max_candidates=1)
        candidates, available, _ = matcher.candidates({'noisy_name': 'Alex Kim'})
        self.assertEqual(len(candidates), 1)
        self.assertGreaterEqual(available, 2)
        authors = [row[0] for row in self.database.execute('SELECT id FROM authors ORDER BY id')]
        self.database.execute('INSERT INTO entity_resolution_matches VALUES(?,?,?,?,?)', ('x', authors[0], 1, 'matched', '{}'))
        self.database.execute('INSERT INTO entity_resolution_candidates VALUES(?,?)', ('x', json.dumps(authors)))
        truth = self.path / 'truth.jsonl'
        truth.write_text(json.dumps({'record_id': 'x', 'source_author_id': authors[1]}) + '\n')
        report = evaluate_resolution(self.database, truth)
        self.assertEqual(report['incorrect_merges'], 1)
        self.assertEqual(report['precision'], 0)
        self.assertEqual(report['candidate_recall'], 1)

    def test_matcher_never_uses_hidden_truth_and_duplicate_inputs_roll_back(self):
        observations = self.path / 'noisy.jsonl'
        record = {'record_id': 'one', 'noisy_name': 'Alex Kim', 'observed_venues': ['Graph Journal'], 'observed_years': [2018]}
        observations.write_text(json.dumps(record) + '\n')
        first = resolve_records(self.database, observations)
        state = [tuple(row) for row in self.database.execute('SELECT * FROM entity_resolution_matches')]
        observations.with_suffix('.truth.jsonl').write_text('not valid JSON; the matcher must not open this file')
        second = resolve_records(self.database, observations)
        self.assertEqual(first['matched'], second['matched'])
        resolved = GraphQueries(self.database).profile_by_observation('one')
        self.assertEqual(resolved['name'], 'Alex Kim 0001')
        self.assertTrue(resolved['publications'])
        self.assertEqual(state, [tuple(row) for row in self.database.execute('SELECT * FROM entity_resolution_matches')])
        observations.write_text((json.dumps(record) + '\n') * 2)
        with self.assertRaises(ValueError):
            resolve_records(self.database, observations)
        self.assertEqual(state, [tuple(row) for row in self.database.execute('SELECT * FROM entity_resolution_matches')])

    def test_profile_and_undirected_shortest_path_return_paper_evidence(self):
        build_context_graph(self.database)
        a = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0001'").fetchone()[0]
        b = self.database.execute("SELECT id FROM authors WHERE canonical_name='Bea Müller'").fetchone()[0]
        c = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0002'").fetchone()[0]
        graph = GraphQueries(self.database)
        path = graph.collaboration_path(b, a)
        self.assertEqual(path['person_ids'], [b, a])
        self.assertEqual(path['edges'][0]['evidence'][0]['paper_id'], 'history/graph')
        self.assertEqual(graph.collaboration_path(a, c)['person_ids'], [])
        self.assertEqual(graph.collaboration_path(a, a)['person_ids'], [a])
        self.assertEqual(graph.profile(a)['publications'][0]['source'], 'dblp')
        self.assertEqual(graph.collaboration_path(a, b, max_hops=0)['person_ids'], [])
        with self.assertRaises(ValueError):
            graph.collaboration_path(-1, b)


if __name__ == '__main__':
    unittest.main()
