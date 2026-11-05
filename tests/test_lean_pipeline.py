"""The compact data path keeps later authorship out of historical graphs."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hiresense.data.artifacts import digest_file
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.split import dataset_digest
from hiresense.models import GroundTruthQuery

ROOT = Path(__file__).resolve().parents[1]


class LeanPipelineTests(unittest.TestCase):
    def test_temporal_selection_and_reserved_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = root / 'source.xml'
            xml.write_text('<dblp>' + ''.join(
                f'<inproceedings key="conf/demo/p{year}"><author>Alice Smith</author>'
                f'<title>Distinct topic {year}</title><year>{year}</year></inproceedings>'
                for year in (2019, 2021, 2023, 2024, 2025)) + '</dblp>')
            database = connect(root / 'source.sqlite3')
            initialize(database)
            report = ingest(database, xml)
            source_hash = dataset_digest(database)
            author = database.execute('SELECT id FROM authors').fetchone()[0]
            database.close()
            (root / 'ingestion.json').write_text(json.dumps(report))
            windows = []
            for year in (2021, 2023, 2024):
                window = root / str(year)
                window.mkdir()
                query = {'query_id': f'conf/demo/p{year}', 'source_paper_id': f'conf/demo/p{year}',
                         'text': f'Distinct topic {year}', 'year': year, 'relevant_author_ids': [author]}
                labels = window / 'labels.jsonl'
                labels.write_text(json.dumps(query) + '\n')
                (window / 'manifest.json').write_text(json.dumps({'labels_sha256': digest_file(labels),
                                                                   'source_dataset_sha256': source_hash}))
                windows.append(str(window))
            config = {'source_db': str(root / 'source.sqlite3'), 'source_xml': str(xml),
                      'source_ingestion_report': str(root / 'ingestion.json'), 'output': str(root / 'out'),
                      'min_year': 1995, 'max_year': 2025, 'query_prefixes': ['conf/demo/'],
                      'additional_history_prefixes': [], 'train_windows': windows[:2],
                      'validation_window': windows[2], 'previous_evaluation_labels': [],
                      'seed': 42, 'test_sample_size': 5}
            (root / 'config.json').write_text(json.dumps(config))
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_lean.py'), '--config', str(root / 'config.json')],
                                 text=True, capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            train = connect(root / 'out/train/graph.sqlite3')
            validation = connect(root / 'out/validation/graph.sqlite3')
            try:
                self.assertEqual(train.execute('SELECT MAX(year) FROM papers').fetchone()[0], 2019)
                self.assertEqual(validation.execute('SELECT MAX(year) FROM papers').fetchone()[0], 2023)
            finally:
                train.close()
                validation.close()
            reserved = json.loads((root / 'out/reserved-test-ids.json').read_text())
            self.assertEqual(reserved['source_paper_ids'], ['conf/demo/p2025'])
            self.assertNotIn('relevant_author_ids', json.dumps(reserved))
            experiments = root / 'resources/experiments'
            experiments.mkdir(parents=True)
            (experiments / 'lean-data.json').write_text(json.dumps(config))
            (experiments / 'lean-test-ids.json').write_text(json.dumps(reserved))
            locked = {'source_archive_sha256': digest_file(xml), 'source_dataset_sha256': source_hash, 'windows': {}}
            for role, cutoff in [('train', 2020), ('validation', 2023)]:
                labels = root / 'out' / role / 'labels.jsonl'
                locked['windows'][role] = {'cutoff': cutoff, 'labels_sha256': digest_file(labels),
                                           'labels': labels.read_text().splitlines()}
            (experiments / 'lean-cohorts.json').write_text(json.dumps(locked))
            rebuilt = subprocess.run([sys.executable, str(ROOT / 'scripts/rebuild_lean_data.py'), '--archive', str(xml),
                                      '--out', str(root / 'rebuilt')], cwd=root, text=True, capture_output=True, timeout=30)
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            self.assertEqual(digest_file(root / 'rebuilt/train/labels.jsonl'), locked['windows']['train']['labels_sha256'])
            config['output'] = str(root / 'mismatch')
            (root / 'config.json').write_text(json.dumps(config))
            (root / 'expected.json').write_text(json.dumps({'source_paper_ids': ['conf/demo/other']}))
            mismatch = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_lean.py'), '--config', str(root / 'config.json'),
                                       '--expected-test-ids', str(root / 'expected.json')],
                                      text=True, capture_output=True, timeout=30)
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertFalse((root / 'mismatch').exists())
            config['output'] = str(root / 'out')
            (root / 'config.json').write_text(json.dumps(config))
            rerun = subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_lean.py'), '--config', str(root / 'config.json')],
                                   text=True, capture_output=True, timeout=30)
            self.assertNotEqual(rerun.returncode, 0)

    def test_retrieval_metrics_keep_missing_history_in_denominator(self):
        spec = importlib.util.spec_from_file_location('evaluate_retrieval', ROOT / 'scripts/evaluate_retrieval.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        queries = [GroundTruthQuery('q1', 'a', 'p1', 2024, (1, 2)),
                   GroundTruthQuery('q2', 'b', 'p2', 2024, (3,))]
        result = module.summarize([(queries[0], [1]), (queries[1], [])], {1})
        self.assertEqual(result['history_coverage'], 1 / 3)
        self.assertEqual(result['candidate_recall_all'], 1 / 3)
        self.assertEqual(result['candidate_recall_known'], 1)
        self.assertEqual(result['queries_with_relevant_candidate'], .5)
        self.assertEqual(result['mrr'], .5)


if __name__ == '__main__':
    unittest.main()
