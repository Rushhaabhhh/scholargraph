"""Chronological test preparation rejects evidence overlap before evaluation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hiresense.contracts import SplitConfig
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.split import dataset_digest, export_snapshot, write_split

ROOT = Path(__file__).resolve().parents[1]


class RollingTests(unittest.TestCase):
    def test_reserved_sample_rejects_test_paper_title_in_newer_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            source = connect(path / 'source.sqlite3')
            initialize(source)
            ingest(source, ROOT / 'tests/fixtures/temporal.xml')
            write_split(source, path / 'parent', SplitConfig(2019, 2020, 2021, 2022))
            export_snapshot(source, path / 'recent.sqlite3', 2021, dataset_digest(source))
            source.close()
            plan = {'reserved_parent': str(path / 'parent'), 'inference_graph_cutoff_year': 2021,
                    'sample_size': 1, 'seed': 42, 'reserved_label_years': [2022]}
            (path / 'plan.json').write_text(json.dumps(plan))
            command = [sys.executable, str(ROOT / 'scripts/prepare_rolling_test.py'), '--plan', str(path / 'plan.json'),
                       '--graph', str(path / 'recent.sqlite3'), '--out', str(path / 'reserved')]
            result = subprocess.run(command, text=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((path / 'reserved/manifest.json').read_text())
            self.assertEqual(manifest['test_count'], 1)
            graph = connect(path / 'recent.sqlite3')
            graph.execute("UPDATE papers SET title_key='future expert discovery' WHERE id='history/graph'")
            graph.commit()
            graph.close()
            command[-1] = str(path / 'blocked')
            result = subprocess.run(command, text=True, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((path / 'blocked').exists())


if __name__ == '__main__':
    unittest.main()
