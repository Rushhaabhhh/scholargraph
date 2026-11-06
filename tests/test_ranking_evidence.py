import unittest
from types import SimpleNamespace
import numpy as np
from hiresense.ranking.evidence import EVIDENCE_FEATURES, evidence_features


class EvidenceFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.index=SimpleNamespace(anchor_year=2020,
            author_papers={1:[0,1,2],2:[3]},
            papers=[{'year':2018},{'year':2020},{'year':2021},{'year':2020}],
            title_tokens=[{'graph'}, {'graph'}, {'graph'}, {'image'}])
        self.context={'similarities':np.array([.8,.5,.99,.9]),'lexical_scores':{0:2.,1:1.,2:10.,3:3.}}

    def test_future_paper_is_excluded_even_when_it_has_highest_score(self):
        before=evidence_features(self.index,self.context,1,'graph')
        self.context['similarities'][2]=.01
        self.context['lexical_scores'][2]=100.
        self.assertEqual(before,evidence_features(self.index,self.context,1,'graph'))
        self.assertEqual(len(before),len(EVIDENCE_FEATURES))

    def test_year_filter_and_author_boundaries(self):
        all_years=evidence_features(self.index,self.context,1,'graph')
        filtered=evidence_features(self.index,{**self.context,'since_year':2020},1,'graph')
        self.assertGreater(all_years[EVIDENCE_FEATURES.index('strong_papers_log')],filtered[EVIDENCE_FEATURES.index('strong_papers_log')])
        self.assertEqual(evidence_features(self.index,self.context,2,'graph')[EVIDENCE_FEATURES.index('strong_papers_log')],0)
        self.assertEqual(evidence_features(self.index,self.context,999,'graph'),[0.0]*len(EVIDENCE_FEATURES))

if __name__=='__main__':unittest.main()

class GraphEvidenceTests(unittest.TestCase):
    def test_graph_features_require_dated_source_edge(self):
        import sqlite3
        from hiresense.ranking.evidence import graph_features
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('create table context_edges(source_id text,target_id text,edge_type text,source_record_id text,edge_year integer)')
        idx=SimpleNamespace(anchor_year=2020,author_papers={1:[0]},papers=[{'id':'p','year':2020}],paper_authors=[[1,2]],title_tokens=[{'graph'}],database=db,degree={2:4})
        ctx={'similarities':np.array([.8])}
        self.assertEqual(graph_features(idx,ctx,1,'graph'),[0.,0.,0.])
        db.execute("insert into context_edges values('author:1','author:2','coauthorship','p',2020)")
        self.assertEqual(graph_features(idx,ctx,1,'graph'),[.8,.8,.4])
        idx.papers[0]['year']=2021
        self.assertEqual(graph_features(idx,ctx,1,'graph'),[0.,0.,0.])
        db.close()
