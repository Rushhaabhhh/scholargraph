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
                       str(ROOT / 'examples/sample.xml'), '--out', str(output)]
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'src')),
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            preparation = json.loads(result.stdout)
            self.assertEqual(preparation['snapshot']['papers'], 200)
            self.assertFalse((output / 'source.sqlite3').exists())
            with TestClient(create_app(preparation['config'])) as client:
                search = client.post('/search', json={'query': 'graph neural networks'}).json()
                self.assertTrue(search['results'])
                self.assertTrue(all(claim['supported'] for person in search['results'] for claim in person['claims']))
                self.assertEqual(client.get('/health').json()['papers'], 200)
