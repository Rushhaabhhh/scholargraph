"""Evidence retrieval retains temporal eligibility and covers the neural shortlist."""
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
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.evidence import EvidenceIndex, EVIDENCE_FEATURES
from hiresense.retrieval.index import build_index

ROOT=Path(__file__).resolve().parents[1]


class CountingCrossEncoder:
    signature='counting-test-model'
    def score(self, query, titles):
        return np.asarray([len(set(query.lower().split()) & set(t.lower().split())) for t in titles],dtype=np.float32)


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.encoder=LocalEncoder()

    def test_shortlist_receives_one_evidence_score_before_second_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);source=connect(path/'source.sqlite3');initialize(source)
            xml='<dblp>'+''.join(f'<article key="p{i}"><author>Author {i}</author><title>Graph neural networks topic {i}</title><year>2019</year></article>' for i in range(8))+'</dblp>'
            (path/'source.xml').write_text(xml);ingest(source,path/'source.xml')
            build_context_graph(source,2019);build_index(source,path/'index',self.encoder)
            engine=EvidenceIndex(source,path/'index',self.encoder,profiles=path/'profiles',cross_encoder=CountingCrossEncoder(),cross_paper_limit=4,cross_author_limit=4,candidate_limit=8)
            try:
                result=engine.retrieve('graph neural networks')
                self.assertEqual(result['features'].shape,(8,len(EVIDENCE_FEATURES)))
                self.assertEqual(len(result['diagnostics']['neural_shortlist']),4)
                for author in result['diagnostics']['neural_shortlist']:
                    row=result['author_ids'].index(author)
                    self.assertEqual(result['features'][row,19],1)
                self.assertEqual(result['diagnostics']['scored_papers'],4)
                self.assertTrue(np.isfinite(result['features']).all())
            finally:engine.close();source.close()

    def test_date_constraint_changes_candidates_features_and_evidence_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);source=connect(path/'source.sqlite3');initialize(source)
            (path/'source.xml').write_text('<dblp>'
                '<article key="old"><author>Old Author</author><title>Graph neural recommendation</title><year>2010</year></article>'
                '<article key="same-old"><author>Mixed Author</author><title>Graph neural recommendation</title><year>2011</year></article>'
                '<article key="new"><author>Mixed Author</author><title>Database storage</title><year>2023</year></article>'
                '<article key="other"><author>Recent Author</author><title>Graph neural recommendation</title><year>2024</year></article></dblp>')
            ingest(source,path/'source.xml');build_context_graph(source,2024);build_index(source,path/'index',self.encoder)
            engine=EvidenceIndex(source,path/'index',self.encoder,profiles=path/'profiles',cross_encoder=CountingCrossEncoder())
            try:
                result=engine.retrieve('graph neural recommendation',since_year=2023)
                self.assertNotIn('Old Author',[engine.authors[a] for a in result['author_ids']])
                for a in result['author_ids']:
                    self.assertTrue(all(engine.papers[i]['year']>=2023 for i in result['evidence'][a]))
                    if engine.authors[a]=='Mixed Author':
                        row=result['author_ids'].index(a)
                        self.assertEqual(result['features'][row,5],0)
                        self.assertEqual(result['features'][row,15],0)
                        self.assertEqual(result['features'][row,20],0)
                        self.assertAlmostEqual(result['features'][row,12],result['features'][row,1],places=6)
                self.assertEqual(engine.retrieve('graph',since_year=9999)['author_ids'],[])
                self.assertEqual(engine.retrieve('')['features'].shape,(0,len(EVIDENCE_FEATURES)))
                before=engine.retrieve('graph')
                excluded=before['author_ids'][0]
                self.assertNotIn(excluded,engine.retrieve('graph',excluded_ids=[excluded])['author_ids'])
            finally:engine.close();source.close()

    def test_multiple_topic_profiles_are_historical_and_fail_closed_on_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);source=connect(path/'source.sqlite3');initialize(source)
            xml='<dblp>'+''.join(f'<article key="p{i}"><author>Mixed Researcher</author><title>{"Graph neural recommendation" if i%2 else "Database transaction storage"} {i}</title><year>{2010+i}</year></article>' for i in range(12))+'</dblp>'
            (path/'source.xml').write_text(xml);ingest(source,path/'source.xml')
            build_context_graph(source,2021);build_index(source,path/'index',self.encoder)
            engine=EvidenceIndex(source,path/'index',self.encoder,profiles=path/'profiles')
            try:
                self.assertEqual(engine.profile_counts.tolist(),[3])
                self.assertEqual(engine.profile_vectors.shape,(3,self.encoder.dimensions))
                self.assertTrue(np.isfinite(engine.retrieve('database transactions')['features']).all())
            finally:engine.close()
            (path/'profiles/counts.npy').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Corrupted'):
                EvidenceIndex(source,path/'index',self.encoder,profiles=path/'profiles')
            source.close()

    def test_rolling_training_merge_preserves_groups_and_rejects_overlap(self):
        from hiresense.evaluation.recovery import merge_training
        from hiresense.models import GroundTruthQuery
        def cache(key):
            return {'queries':[GroundTruthQuery(key,key,key,2023,(1,))],
                    'features':np.zeros((2,len(EVIDENCE_FEATURES))), 'author_ids':np.array([1,2]),
                    'offsets':np.array([0,2]),'lexical':np.array([[1,2]]),'dense':np.array([[1,2]])}
        a,b=cache('a'),cache('b')
        merged=merge_training([a,b])
        self.assertEqual(merged['offsets'].tolist(),[0,2,4])
        self.assertEqual(len(merged['queries']),2)
        with self.assertRaisesRegex(ValueError,'overlap'):merge_training([a,a])
