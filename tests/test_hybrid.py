"""Historical profile retrieval, real pair scoring and portable query-grouped training."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hiresense.contracts import SplitConfig
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.split import write_split
from hiresense.graph.build import build_context_graph
from hiresense.models import GroundTruthQuery
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.hybrid import HYBRID_FEATURES, HybridIndex
from hiresense.retrieval.index import build_index

ROOT = Path(__file__).resolve().parents[1]


class HybridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoder = LocalEncoder()
        cls.cross = CrossEncoder(ROOT / 'models/crossencoder')

    def test_pair_model_understands_specificity(self):
        values = self.cross.score('graph neural networks for recommendation',
                                 ['Graph neural networks for recommender systems.',
                                  'Neural network hardware acceleration.', 'Cooking rice.'])
        self.assertGreater(values[0], values[1] + 1)
        self.assertGreater(values[0], values[2] + 1)
        self.assertEqual(len(self.cross.score('empty', [])), 0)

    def test_profiles_graph_and_cross_scores_remain_historical_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            source = connect(path / 'source.sqlite3')
            initialize(source)
            ingest(source, ROOT / 'tests/fixtures/temporal.xml')
            write_split(source, path / 'dataset', SplitConfig(2019, 2020, 2021, 2022))
            graph = connect(path / 'dataset/graph.sqlite3')
            engine = None
            try:
                build_context_graph(graph)
                build_index(graph, path / 'index', self.encoder)
                engine = HybridIndex(graph, path / 'index', self.encoder, profiles=path / 'profiles',
                                     cross_encoder=self.cross, candidate_limit=10)
                first, second = engine.retrieve('historical graph algorithms'), engine.retrieve('historical graph algorithms')
                self.assertEqual(first['author_ids'], second['author_ids'])
                np.testing.assert_allclose(first['features'], second['features'])
                self.assertEqual(first['features'].shape[1], len(HYBRID_FEATURES))
                self.assertTrue(np.isfinite(first['features']).all())
                self.assertTrue((first['features'][:, -1] == 1).all())
                self.assertTrue(all(engine.papers[i]['year'] <= 2019 for ids in first['evidence'].values() for i in ids))
                self.assertNotIn('New Person', [engine.authors[a] for a in first['author_ids']])
                self.assertEqual(engine.retrieve('')['features'].shape, (0, len(HYBRID_FEATURES)))
                changed = json.loads((path / 'profiles/manifest.json').read_text())
                changed['signature']['cutoff'] = 9999
                (path / 'profiles/manifest.json').write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    HybridIndex(graph, path / 'index', self.encoder, profiles=path / 'profiles')
            finally:
                if engine:
                    engine.close()
                graph.close()
                source.close()

    @unittest.skipUnless(importlib.util.find_spec('lightgbm'), 'Optional training dependency is not installed')
    def test_query_grouped_training_exports_the_fitted_numeric_model(self):
        from hiresense.ranking.lambdamart import train_lambdamart
        rng = np.random.default_rng(42)
        matrix = rng.random((240, len(HYBRID_FEATURES)), dtype=np.float32)
        ids = np.tile(np.arange(6), 40)
        matrix[:, -3] = (ids == 0).astype(np.float32)
        queries = [GroundTruthQuery(f'q:{i}', f'query {i}', f'paper:{i}', 2020, (0,)) for i in range(40)]
        cache = {'features': matrix, 'author_ids': ids, 'offsets': np.arange(0, 241, 6), 'queries': queries}
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / 'ranker.json'
            result = train_lambdamart(cache, cache, file, {}, settings=[{'n_estimators': 5, 'num_leaves': 3}])
            self.assertEqual(result['queries_used'], 40)
            model = json.loads(file.read_text())
            values = score_model(matrix, model)
            self.assertTrue(np.isfinite(values).all())
            self.assertEqual(model['version'], 'hybrid-lambdamart-v1')
            with self.assertRaisesRegex(ValueError, 'schema'):
                score_model(matrix[:, :-1], model)


if __name__ == '__main__':
    unittest.main()
