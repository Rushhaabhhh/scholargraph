"""The recovery experiment keeps labels sealed and model exports portable."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hiresense.evaluation.recovery import discovery_diagnostics
from hiresense.models import GroundTruthQuery
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.evidence import EVIDENCE_FEATURES


class RecoveryTests(unittest.TestCase):
    def test_diagnostics_distinguish_missing_history_retrieval_and_ranking(self):
        queries=[GroundTruthQuery('a','a','a',2025,(9,)),GroundTruthQuery('b','b','b',2025,(3,)),GroundTruthQuery('c','c','c',2025,(1,))]
        cache={'queries':queries,'features':np.zeros((6,len(EVIDENCE_FEATURES))),
               'author_ids':np.array([1,2,1,2,2,1]),'offsets':np.array([0,2,4,6])}
        report=discovery_diagnostics(cache,{1,2,3})
        self.assertEqual(report['counts']['no_history_queries'],1)
        self.assertEqual(report['counts']['retrieval_miss_queries'],1)
        self.assertEqual(report['counts']['hit_at_10'],1)
        self.assertAlmostEqual(report['candidate_oracle']['mrr'],1/3)
        self.assertAlmostEqual(report['graph_oracle']['mrr'],2/3)

    def test_query_adapter_is_portable_and_rejects_invalid_parameters(self):
        from hiresense.retrieval.adaptation import QueryAdapter
        model={'version':'query-residual-ridge-v1','matrix':[[0.,1.],[0.,0.]],'bias':[0.,0.]}
        adapter=QueryAdapter(model,2)
        np.testing.assert_allclose(adapter.transform(np.array([1.,0.])),np.array([1.,1.])/np.sqrt(2),atol=1e-6)
        self.assertEqual(adapter.signature,QueryAdapter(json.loads(json.dumps(model)),2).signature)
        with self.assertRaisesRegex(ValueError,'dimensions'):QueryAdapter(model,3)
        with self.assertRaisesRegex(ValueError,'Invalid query vector'):adapter.transform(np.array([float('nan'),0.]))

    @unittest.skipUnless(importlib.util.find_spec('lightgbm'),'Optional trainer absent')
    def test_evidence_ranker_export_accepts_its_full_feature_schema(self):
        from hiresense.ranking.lambdamart import train_lambdamart
        rng=np.random.default_rng(11);ids=np.tile(np.arange(5),30)
        features=rng.random((150,len(EVIDENCE_FEATURES)),dtype=np.float32)
        features[:,20]=(ids==0).astype(np.float32)
        cache={'queries':[GroundTruthQuery(str(i),str(i),str(i),2024,(0,)) for i in range(30)],
               'features':features,'author_ids':ids,'offsets':np.arange(0,151,5)}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.json'
            train_lambdamart(cache,cache,path,{},feature_names=EVIDENCE_FEATURES,
                             settings=[{'n_estimators':4,'num_leaves':3}])
            model=json.loads(path.read_text())
            self.assertEqual(model['version'],'evidence-lambdamart-v2')
            self.assertTrue(np.isfinite(score_model(features,model)).all())
            with self.assertRaisesRegex(ValueError,'schema'):score_model(features[:,:20],model)
