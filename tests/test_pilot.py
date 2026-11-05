"""Pilot cohorts are reproducible, disjoint and exclude prior-source records."""
import tempfile
import unittest
from pathlib import Path

from hiresense.contracts import SplitConfig
from hiresense.data.ingest import ingest
from hiresense.db import connect, initialize
from hiresense.evaluation.features import load_partition
from hiresense.evaluation.pilot import create_pilot
from hiresense.evaluation.split import write_split

FIXTURE = Path(__file__).parent / 'fixtures/temporal.xml'


class PilotTests(unittest.TestCase):
    def test_fixed_cohorts_and_blind_test_are_separate_from_model_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = connect(root / 'source.sqlite3')
            initialize(source)
            ingest(source, FIXTURE)
            write_split(source, root / 'dataset', SplitConfig(2019, 2020, 2021, 2022))
            graph = connect(root / 'dataset/graph.sqlite3')
            excluded = connect(root / 'previous.sqlite3')
            initialize(excluded)
            ingest(excluded, FIXTURE)
            excluded.execute('DELETE FROM papers WHERE year > 2019')
            excluded.commit()
            try:
                first = create_pilot(root / 'dataset', graph, excluded, root / 'pilot-a',
                                     train_count=1, validation_count=1, test_start=2022)
                second = create_pilot(root / 'dataset', graph, excluded, root / 'pilot-b',
                                      train_count=1, validation_count=1, test_start=2022)
                self.assertEqual(first, second)
                self.assertEqual(first['selection']['reserved_test_count'], 1)
                train, _ = load_partition(root / 'pilot-a', 'train', graph)
                valid, _ = load_partition(root / 'pilot-a', 'validation', graph)
                test, _ = load_partition(root / 'pilot-a', 'test', graph)
                self.assertEqual([q.year for q in train + valid + test], [2020, 2021, 2022])
                self.assertEqual(len({q.source_paper_id for q in train + valid + test}), 3)
                (root / 'pilot-a/test_ground_truth.jsonl').write_text('invalid and intentionally unread')
                self.assertEqual(len(load_partition(root / 'pilot-a', 'train', graph)[0]), 1)
                with self.assertRaisesRegex(ValueError, 'manifest'):
                    load_partition(root / 'pilot-a', 'test', graph)
                with self.assertRaises(ValueError):
                    create_pilot(root / 'dataset', graph, excluded, root / 'invalid',
                                 train_count=1, validation_count=1, test_start=2021)
                self.assertFalse((root / 'invalid').exists())
                excluded.execute("INSERT INTO papers(id,title,title_key,year) VALUES(?,?,?,?)",
                                 ('old/duplicate', 'Future expert discovery', 'future expert discovery', 2017))
                with self.assertRaisesRegex(ValueError, 'test cohort is empty'):
                    create_pilot(root / 'dataset', graph, excluded, root / 'blocked',
                                 train_count=1, validation_count=1, test_start=2022)
                self.assertFalse((root / 'blocked').exists())
            finally:
                graph.close()
                excluded.close()
                source.close()


if __name__ == '__main__':
    unittest.main()
