import unittest
import sqlite3
from types import SimpleNamespace
import numpy as np
from hiresense.evaluation.phase1_retrieval import aggregate_papers, fuse_author_ranks, topical_neighbors


class PhaseOneAggregationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE context_edges (source_id TEXT,target_id TEXT,edge_type TEXT,source_record_id TEXT,edge_year INTEGER)')
        self.db.execute("INSERT INTO context_edges VALUES ('author:3','author:4','coauthorship','p3',2023)")
        self.index = SimpleNamespace(paper_limit=4, anchor_year=2023,
            database=self.db,
            paper_authors=[[1], [2], [2], [3, 4]],
            author_papers={1:[0], 2:[1,2], 3:[3], 4:[3]},
            papers=[{'id':f'p{i}','year':year} for i,year in enumerate((2020,2021,2022,2023))],
            title_tokens=[{'graph'}, {'graph'}, {'graph'}, {'image'}])
        self.context={'similarities':np.array([.9,.8,.7,.1]), 'lexical_scores':{0:1.,1:.8,2:.7,3:.1}}

    def test_multiple_papers_can_improve_author_position_without_changing_pool(self):
        maximum=aggregate_papers(self.index,self.context,'max')
        top=aggregate_papers(self.index,self.context,'top3')
        self.assertEqual(maximum[0],1)
        self.assertEqual(top[0],2)
        self.assertEqual(set(maximum),set(top))
        self.assertEqual(set(aggregate_papers(self.index,self.context,'coverage')),set(top))

    def test_fusion_adds_profile_authors_without_duplicates(self):
        result=fuse_author_ranks([1,2],[2,3])
        self.assertEqual(set(result),{1,2,3})
        self.assertEqual(len(result),3)

    def test_neighbors_require_query_matching_dated_publication(self):
        self.assertEqual(topical_neighbors(self.index,self.context,'graph',[3]),[])
        self.index.title_tokens[3]={'graph'}
        self.context['similarities'][3]=.8
        self.assertEqual(topical_neighbors(self.index,self.context,'graph',[3]),[4])
        self.db.execute('DELETE FROM context_edges')
        self.assertEqual(topical_neighbors(self.index,self.context,'graph',[3]),[])
        self.index.papers[3]['year']=2024
        self.assertEqual(topical_neighbors(self.index,self.context,'graph',[3]),[])

    def tearDown(self):
        self.db.close()

if __name__ == '__main__':
    unittest.main()
