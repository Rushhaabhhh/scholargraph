"""Exercise the real rolling trainer/adapter/export entrypoint on a tiny fixture."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from hiresense.data.artifacts import digest_file,write_json
from hiresense.data.ingest import ingest
from hiresense.db import connect,initialize
from hiresense.evaluation.split import dataset_digest,export_snapshot
from hiresense.graph.build import build_context_graph
from hiresense.models import GroundTruthQuery
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import build_index

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('lightgbm'),'Optional training dependency absent')
class RecoveryWorkflowTests(unittest.TestCase):
    def test_rolling_trainer_never_opens_a_test_label_file_and_exports_compatible_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);xml=[]
            for a in range(6):
                for i in range(4):
                    xml.append(f'<article key="history/{a}/{i}"><author>Researcher {a}</author><title>Graph learning recommendation research {a} method {i}</title><year>{2017+i}</year><journal>Graph Journal</journal></article>')
            source=connect(path/'source.sqlite3');initialize(source)
            (path/'source.xml').write_text('<dblp>'+''.join(xml)+'</dblp>')
            ingest(source,path/'source.xml');origin=dataset_digest(source)
            author=source.execute("SELECT id FROM authors WHERE canonical_name='Researcher 0'").fetchone()[0]
            encoder=LocalEncoder()
            for role,cutoff,year,count in [('train-early',2020,2021,30),('train-later',2022,2023,30),('validation',2023,2024,12)]:
                directory=path/role;directory.mkdir()
                export_snapshot(source,directory/'graph.sqlite3',cutoff,origin)
                graph=connect(directory/'graph.sqlite3');build_context_graph(graph);build_index(graph,directory/'index',encoder);graph.close()
                queries=[GroundTruthQuery(f'{role}/{i}',f'Graph learning recommendation {role} study {i}',f'{role}/{i}',year,(author,)) for i in range(count)]
                labels=directory/'labels.jsonl';labels.write_text(''.join(json.dumps(asdict(q))+'\n' for q in queries))
                write_json(directory/'manifest.json',{'labels_sha256':digest_file(labels),'source_dataset_sha256':origin,
                    'window':{'role':role,'cutoff':cutoff,'start':year,'end':year,'queries':count}})
            source.close()
            # There is deliberately no test directory: training must not depend on it.
            config={'source_work':str(path),'work':str(path/'training'),'report':str(path/'report.json'),
                'retrieval_report':str(path/'retrieval.json'),'encoder':str(ROOT/'models/minilm'),
                'cross_encoder':str(ROOT/'models/crossencoder'),'train_roles':['train-early','train-later'],
                'validation_role':'validation','seed':17,'selection':'Validation only.',
                'retrieval':{'paper_limit':24,'candidate_limit':6,'profile_limit':6,'author_lexical_limit':6,
                    'expansion_limit':4,'cross_paper_limit':8,'cross_author_limit':6,'topic_profiles':2}}
            write_json(path/'config.json',config)
            result=subprocess.run([sys.executable,str(ROOT/'scripts/train_recovery.py'),'--config',str(path/'config.json')],
                cwd=ROOT,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(ROOT/'src')),
                text=True,capture_output=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr[-4000:])
            report=json.loads((path/'report.json').read_text())
            self.assertEqual(report['scope'],'Train/validation selection only; reserved test not opened.')
            self.assertEqual(report['package_source_sha256_start'],report['package_source_sha256_end'])
            self.assertEqual(report['training']['full']['queries_used'],60)
            self.assertEqual(report['name_counterfactual']['changed_rankings_or_scores'],0)
