"""Prepare a backend from unseen XML and serve its grounded search offline."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from hiresense.api.app import create_app
from hiresense.api.runtime import Backend
from hiresense.assistant.providers import LocalLLMProvider, RecordedProvider
from hiresense.batch import run_batch

ROOT = Path(__file__).resolve().parents[1]


class BackendCliTests(unittest.TestCase):
    def test_batch_launcher_fails_fast_when_current_environment_lacks_dependencies(self):
        code = "import importlib.util,runpy; importlib.util.find_spec=lambda name:None; runpy.run_path(" + repr(str(ROOT / 'run')) + ",run_name='__main__')"
        result = subprocess.run([sys.executable, '-c', code], text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Install the dependencies', result.stderr)

    def test_prepare_command_connects_data_graph_model_api_and_memory(self):
        with tempfile.TemporaryDirectory(prefix='hiresense-cli-backend-') as temporary:
            output = Path(temporary) / 'prepared'
            command = [sys.executable, '-m', 'hiresense.cli', 'prepare-backend', '--data',
                       str(ROOT / 'resources/examples/sample.xml'), '--out', str(output)]
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')),
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            preparation = json.loads(result.stdout)
            config_path = Path(preparation['config'])
            config = json.loads(config_path.read_text())
            self.assertEqual(config['query_provider'], 'local_llm')
            backend = Backend.load(config_path)
            try:
                self.assertIsInstance(backend.understander.provider, LocalLLMProvider)
            finally:
                backend.close()
            # Avoid loading the optional 0.5B model in this offline integration test.
            config['query_provider'] = 'recorded'
            config_path.write_text(json.dumps(config))
            self.assertEqual(preparation['snapshot']['papers'], 200)
            self.assertFalse((output / 'source.sqlite3').exists())
            with TestClient(create_app(preparation['config'])) as client:
                search = client.post('/search', json={'query': 'graph neural networks'}).json()
                self.assertTrue(search['results'])
                self.assertTrue(all(claim['supported'] for person in search['results'] for claim in person['claims']))
                self.assertEqual(client.get('/health').json()['papers'], 200)
                queries = Path(temporary) / 'queries.txt'
                queries.write_text('graph neural networks\n', encoding='utf-8')
                batch_path = Path(temporary) / 'batch.json'
                run_batch(str(ROOT / 'resources/examples/sample.xml'), str(queries), str(batch_path))
                batch = json.loads(batch_path.read_text())[0]
                self.assertEqual([r['person_id'] for r in batch['results']],
                                 [r['person_id'] for r in search['results']])
                self.assertEqual([r['score'] for r in batch['results']],
                                 [r['score'] for r in search['results']])
            # Configurations produced before the resource move remain usable.
            config['query_provider'] = 'recorded'
            config['recordings'] = str(ROOT / 'recordings/query-intents.json')
            config_path.write_text(json.dumps(config))
            backend = Backend.load(config_path)
            try:
                self.assertIsInstance(backend.understander.provider, RecordedProvider)
            finally:
                backend.close()
