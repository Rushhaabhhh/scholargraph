import csv,json,subprocess,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class HumanReviewTests(unittest.TestCase):
    def test_blank_grades_cannot_be_reported_as_human_results(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'result.json'
            p=subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_human_review.py'),'--reviews',str(ROOT/'resources/experiments/phase3-review-template.csv'),'--out',str(output)],cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('No actual human judgments',p.stderr)
            self.assertFalse(output.exists())

    def test_partial_judgments_remain_unjudged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pool=root/'pool.jsonl';pool.write_text(json.dumps({'query_id':'q','person_id':1})+'\n'+json.dumps({'query_id':'q','person_id':2})+'\n')
            methods=root/'methods.json';methods.write_text(json.dumps({'methods':[{'query_id':'q','methods':{x:[1,2] for x in ('lexical','dense','hybrid','trained')}}]}))
            reviews=root/'reviews.csv'
            with reviews.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['query_id','person_id','grade_0_to_3','reviewer']);w.writeheader();w.writerow({'query_id':'q','person_id':1,'grade_0_to_3':'3','reviewer':'A'})
            output=root/'result.json';p=subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_human_review.py'),'--reviews',str(reviews),'--pool',str(pool),'--methods',str(methods),'--out',str(output)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            result=json.loads(output.read_text());self.assertEqual(result['pool_coverage'],.5);self.assertIsNone(result['metrics']['trained']['metrics'])

if __name__=='__main__':unittest.main()
