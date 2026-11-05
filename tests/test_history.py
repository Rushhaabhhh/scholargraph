"""History selection is venue/year based and never adds future label records."""
import json
import tempfile
import unittest
from pathlib import Path

from hiresense.data.artifacts import digest_file
from hiresense.data.dblp import iter_publications
from hiresense.data.history import enrich_history


class HistoryTests(unittest.TestCase):
    def test_complete_family_history_excludes_future_and_unrelated_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            base = '<article key="base"><author>A</author><title>Base</title><year>2024</year></article>'
            (path / 'base.xml').write_text('<dblp>' + base + '</dblp>')
            (path / 'raw.xml').write_text('<dblp>' + base +
                '<article key="journals/ml/a"><author>B</author><title>History</title><year>2018</year></article>'
                '<article key="journals/ml/c"><author>E</author><title>Named venue</title><year>2017</year><journal>ML</journal></article>'
                '<article key="journals/ml/b"><author>C</author><title>Future</title><year>2024</year></article>'
                '<article key="journals/ml2/a"><author>D</author><title>Other</title><year>2018</year></article></dblp>')
            (path / 'md5').write_text(digest_file(path / 'raw.xml', 'md5'))
            config = {'archive': str(path / 'raw.xml'), 'baseline': str(path / 'base.xml'),
                      'checksum': str(path / 'md5'), 'min_year': 1995, 'cutoff_year': 2018,
                      'key_prefixes': ['journals/ml/']}
            (path / 'config.json').write_text(json.dumps(config))
            result = enrich_history(path / 'config.json', path / 'result.xml')
            self.assertEqual(result['added_historical_papers'], 2)
            self.assertEqual(result['added_venue_counts'], {'(unknown)': 1, 'ML': 1})
            self.assertEqual([p.key for p in iter_publications(path / 'result.xml')], ['base', 'journals/ml/a', 'journals/ml/c'])
            with self.assertRaises(ValueError):
                enrich_history(path / 'config.json', path / 'result.xml')
