"""Synthetic fixture tests only: no real reviewers or grades are created."""
import copy
import math
import sys
import csv
import json
import tempfile
import subprocess
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from phase5b_evaluate import evaluate, metrics


def fixture():
    master=[];private=[]
    for cohort, year in [('Q01',2024),('P01',2023)]:
        for i in range(10):
            for slot in (('1',) if cohort[0]=='Q' else ('1','2')):
                master.append({'query_id':cohort,'query':'synthetic query','cutoff_year':str(year),'person_id':str(i),
                               'author_name':'synthetic','evidence':'[]','reviewer_slot':slot,'grade_0_to_3':'','reviewer':'','notes':''})
            if cohort=='P01':private.append({'query_id':cohort,'person_id':str(i),'stratum':'A_frozen_model_top10','frozen_model_rank':str(i+1),'proxy_future_author':'0'})
    production={'Q01':list(range(10))}
    return master,private,production

def submitted(master):
    rows=copy.deepcopy(master)
    for r in rows:r['grade_0_to_3']='2' if r['person_id']=='1' else '0';r['reviewer']='reviewer-'+r['reviewer_slot']
    return rows

class EvaluationTests(unittest.TestCase):
    def setUp(self):self.master,self.private,self.production=fixture();self.rows=submitted(self.master)
    def run_eval(self,rows=None,master=None):return evaluate(master or self.master, self.rows if rows is None else rows,self.production,self.private,n_bootstrap=100)
    def test_cli_with_isolated_synthetic_fixture_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name,rows in [('master.csv',self.master),('review.csv',self.rows),('private.csv',self.private)]:
                with (root/name).open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
            (root/'production.json').write_text(json.dumps({'queries':self.production}))
            cmd=[sys.executable,'scripts/phase5b_evaluate.py','--master',str(root/'master.csv'),'--reviews',str(root/'review.csv'),'--private',str(root/'private.csv'),'--production',str(root/'production.json'),'--out',str(root/'report.json')]
            completed=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            report=json.loads((root/'report.json').read_text());self.assertAlmostEqual(report['cohorts']['Q']['metrics']['mrr_at_10'],.5)
    def test_hand_computed_metrics(self):
        m=metrics([0,2]+[0]*8,[0,2]+[0]*8)
        self.assertAlmostEqual(m['ndcg_at_10_pooled_ideal'],1/math.log2(3));self.assertEqual(m['precision_at_10'],.1);self.assertEqual(m['mrr_at_10'],.5)
    def test_separate_cohorts_and_complete_metrics(self):
        r=self.run_eval();self.assertEqual(r['cohorts']['Q']['queries'],1);self.assertEqual(r['cohorts']['P']['queries'],1);self.assertAlmostEqual(r['cohorts']['Q']['metrics']['mrr_at_10'],.5)
        self.assertEqual(r['reviewer_agreement']['exact_agreement'],1)
    def test_bootstrap_is_deterministic(self):
        first=self.run_eval();second=self.run_eval()
        self.assertEqual(first['cohorts']['P']['query_bootstrap_95'],second['cohorts']['P']['query_bootstrap_95'])
    def test_partial_double_review_is_not_a_grade(self):
        row=next(x for x in self.rows if x['query_id']=='P01' and x['person_id']=='1' and x['reviewer_slot']=='2');row['grade_0_to_3']=''
        result=self.run_eval();self.assertEqual(result['query_results']['P01']['frozen_model']['judged_top10'],9);self.assertIsNone(result['cohorts']['P']['metrics'])
    def test_unknown_id_rejected(self):
        self.rows[0]['person_id']='missing'
        with self.assertRaisesRegex(ValueError,'Unknown query'):self.run_eval()
    def test_duplicate_slot_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate submitted'):self.run_eval(self.rows+[copy.deepcopy(self.rows[0])])
    def test_blank_submission_rejected(self):
        with self.assertRaisesRegex(ValueError,'No completed'):self.run_eval(copy.deepcopy(self.master))
    def test_partial_does_not_publish_aggregate(self):
        self.rows[0]['grade_0_to_3']='';r=self.run_eval()
        self.assertIsNone(r['cohorts']['Q']['metrics']);self.assertIsNotNone(r['cohorts']['P']['metrics']);self.assertEqual(r['cohorts']['Q']['coverage'],.9)
    def test_unable_distinct_from_blank_and_zero(self):
        self.rows[0].update(grade_0_to_3='U',notes='identity unclear');self.rows[1]['grade_0_to_3']='';r=self.run_eval()
        self.assertEqual(r['review_slots']['unable'],1);self.assertEqual(r['review_slots']['blank'],1);self.assertTrue(any(x['status']=='unable_to_judge' for x in r['unresolved']));self.assertIsNone(r['cohorts']['Q']['metrics'])
    def test_unable_requires_reason(self):
        self.rows[0]['grade_0_to_3']='U'
        with self.assertRaisesRegex(ValueError,'require a reason'):self.run_eval()
    def test_reviewer_disagreement_and_consensus(self):
        row=next(x for x in self.rows if x['query_id']=='P01' and x['person_id']=='0' and x['reviewer_slot']=='2');row['grade_0_to_3']='3';r=self.run_eval()
        self.assertEqual(r['reviewer_agreement']['double_graded_pairs'],10);self.assertAlmostEqual(r['reviewer_agreement']['exact_agreement'],.9);self.assertEqual(len(r['reviewer_agreement']['disagreements']),1)
    def test_same_reviewer_cannot_double_review(self):
        row=next(x for x in self.rows if x['query_id']=='P01' and x['person_id']=='0' and x['reviewer_slot']=='2');row['reviewer']='reviewer-1'
        with self.assertRaisesRegex(ValueError,'multiple slots'):self.run_eval()
    def test_cutoff_cohort_mixing_rejected(self):
        master=copy.deepcopy(self.master);master[0]['cutoff_year']='2023'
        with self.assertRaisesRegex(ValueError,'cutoff mismatch'):self.run_eval(master=master)
    def test_query_evidence_tampering_rejected(self):
        self.rows[0]['evidence']='changed'
        with self.assertRaisesRegex(ValueError,'evidence differs'):self.run_eval()
    def test_incomplete_pool_blocks_ndcg_even_if_top_ten_graded(self):
        extra=copy.deepcopy(self.master[0]);extra['person_id']='11';master=self.master+[extra]
        r=self.run_eval(master=master);self.assertEqual(r['query_results']['Q01']['production']['judged_top10'],10);self.assertIsNone(r['query_results']['Q01']['production']['metrics'])

if __name__=='__main__':unittest.main()
