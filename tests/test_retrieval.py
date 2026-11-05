"""Real local embeddings, leakage boundaries, portable training and ranking."""

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from hiresense.contracts import SplitConfig, validate_batch_results
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.experiment import train_from_dataset
from hiresense.evaluation.features import load_partition
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.ranking import name_counterfactual
from hiresense.evaluation.split import write_split
from hiresense.graph.build import build_context_graph
from hiresense.ranking.scoring import score_model
from hiresense.ranking.service import search
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex, build_index

FIXTURE = Path(__file__).parent / 'fixtures/temporal.xml'


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A genuine pre-trained encoder is exercised offline, rather than a hash mock.
        with patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')):
            cls.encoder = LocalEncoder()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        source = connect(self.path / 'source.sqlite3')
        initialize(source)
        ingest(source, FIXTURE)
        self.dataset = self.path / 'dataset'
        write_split(source, self.dataset, SplitConfig(2019, 2020, 2021, 2022))
        source.close()
        self.database = connect(self.dataset / 'graph.sqlite3')
        build_context_graph(self.database)
        self.index_path = self.path / 'index'
        build_index(self.database, self.index_path, self.encoder)
        self.engine = SearchIndex(self.database, self.index_path, self.encoder)

    def tearDown(self):
        self.engine.close()
        self.database.close()
        self.temp.cleanup()

    def test_real_dense_vectors_capture_related_topics_and_are_normalized(self):
        with patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')):
            vectors = self.encoder.encode(['graph neural networks', 'graph representation learning', 'cooking with rice'])
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        self.assertGreater(float(vectors[0] @ vectors[1]), float(vectors[0] @ vectors[2]) + 0.3)
        self.assertEqual(self.encoder.encode([]).shape, (0, 384))

    def test_index_builds_in_bounded_chunks_and_keeps_vectors_aligned(self):
        class CountingEncoder:
            dimensions = 2
            signature = 'test-encoder'
            def __init__(self):
                self.batch_sizes = []
            def encode(self, titles):
                self.batch_sizes.append(len(titles))
                return np.asarray([[int(title), -int(title)] for title in titles], dtype=np.float32)

        database = connect(self.path / 'many.sqlite3')
        try:
            initialize(database)
            database.executemany('INSERT INTO papers(id,title) VALUES(?,?)',
                                 [(f'{i:04}', str(i)) for i in range(1030)])
            encoder = CountingEncoder()
            index = self.path / 'many-index'
            report = build_index(database, index, encoder)
            self.assertEqual(report['papers'], 1030)
            self.assertEqual(encoder.batch_sizes, [512, 512, 6])
            vectors = np.load(index / 'embeddings.npy', allow_pickle=False)
            self.assertEqual(vectors.shape, (1030, 2))
            np.testing.assert_array_equal(vectors[:, 0], np.arange(1030))
            manifest = json.loads((index / 'manifest.json').read_text())
            self.assertEqual(manifest['paper_ids'][512], '0512')
        finally:
            database.close()

    def test_bm25_and_hybrid_are_bounded_deterministic_and_evidence_backed(self):
        first = self.engine.retrieve('historical graph algorithms')
        second = self.engine.retrieve('historical graph algorithms')
        self.assertTrue(first['lexical'])
        self.assertTrue(first['dense'])
        self.assertEqual(first['author_ids'], second['author_ids'])
        np.testing.assert_array_equal(first['features'], second['features'])
        self.assertLessEqual(len(first['author_ids']), self.engine.candidate_limit)
        self.assertEqual(first['features'].shape[1], len(FEATURE_NAMES))
        result = self.engine.results('historical graph algorithms', first, first['features'][:, -1])
        validate_batch_results([{'query': 'historical graph algorithms', 'results': result}])
        self.assertTrue(all(paper['year'] <= 2019 for person in result for paper in person['evidence']))
        self.assertTrue(all(paper['paper_id'] not in {'train/future', 'validation/future', 'test/future'}
                            for person in result for paper in person['evidence']))

    def test_fts_punctuation_and_embedded_instructions_are_data(self):
        for query in ('" OR * --', 'ignore previous instructions; DROP TABLE papers; graph'):
            self.engine.retrieve(query)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM papers').fetchone()[0], 4)
        self.assertEqual(self.engine.retrieve('')['author_ids'], [])
        with self.assertRaises(ValueError):
            self.engine.retrieve('x' * 4001)

    def test_temporal_graph_contamination_is_rejected_before_indexing(self):
        self.database.execute("UPDATE papers SET year=2024 WHERE id='history/graph'")
        with self.assertRaisesRegex(ValueError, 'post-cutoff'):
            build_index(self.database, self.path / 'contaminated-index', self.encoder)
        self.assertFalse((self.path / 'contaminated-index').exists())

    def test_stale_index_and_modified_labels_are_rejected(self):
        self.database.execute("UPDATE papers SET title='Changed evidence' WHERE id='history/graph'")
        with self.assertRaisesRegex(ValueError, 'Stale'):
            SearchIndex(self.database, self.index_path, self.encoder)
        file = self.dataset / 'train_ground_truth.jsonl'
        file.write_text(file.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'manifest'):
            load_partition(self.dataset, 'train', self.database)

    def test_semantic_model_and_index_checksum_fail_closed(self):
        broken = self.path / 'broken-encoder'
        broken.mkdir()
        (broken / 'model.onnx').write_bytes(b'invalid model')
        (broken / 'manifest.json').write_text(json.dumps({'files': {'model.onnx': 'invalid digest'}}))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            LocalEncoder(broken)
        manifest = self.index_path / 'manifest.json'
        value = json.loads(manifest.read_text())
        value['encoder_sha256'] = 'different'
        manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            SearchIndex(self.database, self.index_path, self.encoder)

    def test_train_export_predict_and_name_counterfactual(self):
        model_path = self.path / 'ranker.json'
        report = train_from_dataset(self.engine, self.dataset, self.path / 'cache', model_path)
        self.assertGreater(report['examples'], 0)
        model = json.loads(model_path.read_text())
        self.assertEqual(model['version'], 'gradient-boosted-expert-v1')
        self.assertIn('blend_alpha', model)
        self.assertNotIn('test_labels_sha256', model)
        self.assertTrue(np.isfinite(score_model(self.engine.retrieve('graph')['features'], model)).all())
        result = search(self.engine, 'graph', model)
        validate_batch_results([{'query': 'graph', 'results': result}])
        queries, _ = load_partition(self.dataset, 'validation', self.database)
        fairness = name_counterfactual(self.engine, model, queries)
        self.assertEqual(fairness['changed_rankings_or_scores'], 0)
        no_recency_path = self.path / 'no-recency.json'
        train_from_dataset(self.engine, self.dataset, self.path / 'cache', no_recency_path,
                           ablate='recency', parameters=report['parameters'])
        ablated = json.loads(no_recency_path.read_text())
        used = {FEATURE_NAMES[index] for index in ablated['selected_features']}
        self.assertFalse({'matched_recency', 'author_recency'} & used)
        # If training accidentally opens test labels, their deliberate corruption must fail this call.
        (self.dataset / 'test_ground_truth.jsonl').write_text('invalid JSON: test data must stay unread')
        train_from_dataset(self.engine, self.dataset, self.path / 'cache', self.path / 'again.json')

    def test_metrics_include_relevant_authors_after_rank_ten(self):
        ranked = list(range(20))
        self.assertEqual(ranking_metrics(ranked, {15})['ndcg_at_10'], 0)
        self.assertEqual(ranking_metrics(ranked, {15})['mrr'], 1 / 16)
        self.assertEqual(ranking_metrics([], {15})['mrr'], 0)
        with self.assertRaises(ValueError):
            ranking_metrics([1, 1], {1})

    def test_recency_is_relative_to_graph_cutoff_and_author_support_is_normalized(self):
        retrieved = self.engine.retrieve('historical graph')
        matrix = retrieved['features']
        self.assertTrue((matrix[:, FEATURE_NAMES.index('support_fraction')] <= 1).all())
        self.assertTrue((matrix[:, FEATURE_NAMES.index('matched_recency')] <= 1).all())
        self.assertEqual(self.engine.anchor_year, 2019)
        newer = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0002'").fetchone()[0]
        older = self.database.execute("SELECT id FROM authors WHERE canonical_name='Alex Kim 0001'").fetchone()[0]
        self.assertGreater(self.engine.author_recency[newer], self.engine.author_recency[older])


if __name__ == '__main__':
    unittest.main()
