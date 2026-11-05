"""Exercise the actual offline command interfaces and their failure boundaries."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_complete_data_workflow_and_rejected_unsafe_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1')

            def run(*args, success=True):
                process = subprocess.run([sys.executable, '-m', 'hiresense.cli', *args], cwd=directory,
                                         env=env, text=True, capture_output=True)
                if success:
                    self.assertEqual(process.returncode, 0, process.stderr)
                    return json.loads(process.stdout)
                self.assertNotEqual(process.returncode, 0)
                self.assertTrue(process.stderr.startswith('hiresense:'))
                return process.stderr

            fixture = str(ROOT / 'tests/fixtures/temporal.xml')
            report = run('ingest', '--data', fixture, '--db', 'source.sqlite3', '--report', 'ingest.json')
            self.assertEqual(report['records_loaded'], 10)
            self.assertTrue((directory / 'ingest.json').is_file())
            manifest = run('prepare', '--db', 'source.sqlite3', '--cutoff-year', '2019', '--train-end-year', '2020',
                           '--validation-end-year', '2021', '--test-end-year', '2022', '--out', 'dataset')
            self.assertEqual(manifest['labels']['test']['queries'], 1)
            noise = run('noise', '--db', 'dataset/graph.sqlite3', '--out', 'noise.jsonl', '--rate', '1')
            self.assertEqual(noise['noisy_records'], 4)
            self.assertTrue((directory / 'noise.truth.jsonl').is_file())
            self.assertIn('snapshot', run('noise', '--db', 'source.sqlite3', '--out', 'bad-noise.jsonl', success=False))
            self.assertIn('does not exist', run('prepare', '--db', 'missing.sqlite3', '--cutoff-year', '2019',
                          '--train-end-year', '2020', '--validation-end-year', '2021', '--test-end-year', '2022', '--out', 'bad', success=False))
            self.assertFalse((directory / 'missing.sqlite3').exists())
            self.assertIn('overwrite', run('ingest', '--data', fixture, '--db', 'source.sqlite3', '--report', 'source.sqlite3', success=False))
            graph = run('graph', '--db', 'dataset/graph.sqlite3')
            self.assertEqual(graph['coauthorship_edges'], 1)
            encoder = str(ROOT / 'models/minilm')
            run('index', '--db', 'dataset/graph.sqlite3', '--encoder', encoder, '--out', 'index')
            trained = run('train', '--db', 'dataset/graph.sqlite3', '--index', 'index', '--encoder', encoder, '--dataset', 'dataset', '--cache', 'features', '--model', 'ranker.json')
            self.assertGreater(trained['examples'], 0)
            metrics = run('evaluate', '--db', 'dataset/graph.sqlite3', '--index', 'index', '--encoder', encoder, '--dataset', 'dataset', '--cache', 'features', '--model', 'ranker.json', '--out', 'ranking.json')
            self.assertEqual(metrics['queries'], 1)


if __name__ == '__main__':
    unittest.main()
