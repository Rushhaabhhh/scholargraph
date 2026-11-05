import gzip
import io
import json
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from hiresense.batch import run_batch
from hiresense.contracts import SplitConfig, validate_batch_results
from hiresense.data.artifacts import digest_file
from hiresense.data.dblp import PUBLICATION_TAGS, iter_publications
from hiresense.data.ingest import ingest
from hiresense.data.noise import generate_noisy_authors
from hiresense.data.slice import create_slice
from hiresense.data.xml_stream import EntityNormalizingReader
from hiresense.db import connect, initialize
from hiresense.evaluation.split import assert_no_leakage, load_queries, write_split

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/temporal.xml'
CONFIG = SplitConfig(2019, 2020, 2021, 2022)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.database = connect(self.directory / 'source.sqlite3')
        initialize(self.database)
        self.report = ingest(self.database, FIXTURE)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def snapshot(self, name='dataset'):
        path = self.directory / name
        manifest = write_split(self.database, path, CONFIG)
        graph = connect(path / 'graph.sqlite3')
        self.addCleanup(graph.close)
        return path, graph, manifest

    def test_all_record_types_nested_text_namespaces_and_entities_offline(self):
        for tag in PUBLICATION_TAGS:
            file = self.directory / f'{tag}.xml'
            file.write_text(f'<dblp xmlns="urn:dblp"><{tag} key="x"><author>Wei Wang 0001</author>'
                            '<title>A <i>nested</i> title &uuml; &amp; end</title><year>2020</year>'
                            f'</{tag}></dblp>', encoding='utf-8')
            publication, = iter_publications(file)
            self.assertEqual(publication.title, 'A nested title ü & end')
            self.assertEqual(publication.record_type, tag)
            self.assertEqual(publication.authors, ('Wei Wang 0001',))
        entities = list(iter_publications(ROOT / 'tests/fixtures/entities.xml'))
        self.assertEqual(entities[0].title, 'A study of ünicode & entities')
        legacy = self.directory / 'latin.xml.gz'
        xml = '<?xml version="1.0" encoding="ISO-8859-1"?><!DOCTYPE dblp SYSTEM "http://127.0.0.1:1/unavailable.dtd"><dblp><article key="x"><title>Müller &uuml;</title></article></dblp>'
        with gzip.open(legacy, 'wb') as stream:
            stream.write(xml.encode('latin-1'))
        self.assertEqual(list(iter_publications(legacy))[0].title, 'Müller ü')

    def test_entity_boundaries_and_stream_closure(self):
        source = io.BytesIO(b'A &uuml; B &#252; &amp; C')
        reader = EntityNormalizingReader(source, chunk_size=3)
        data = b''.join(iter(lambda: reader.read(2), b''))
        self.assertEqual(data, b'A &#252; B &#252; &amp; C')
        reader.close()
        self.assertTrue(source.closed)

    def test_skips_metadata_and_keeps_unknown_year_without_guessing(self):
        self.assertEqual(self.report['parser']['skipped_missing_key_or_title'], 1)
        row = self.database.execute("SELECT year FROM papers WHERE id='unknown/year'").fetchone()
        self.assertIsNone(row[0])
        self.assertEqual(self.report['inserted'], 10)

    def test_idempotency_preserves_every_graph_table_and_stable_ids(self):
        def state(db):
            return {table: [tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY 1,2')]
                    for table in ('papers', 'authors', 'venues', 'paper_authors', 'paper_venues', 'context_edges')}
        before = state(self.database)
        repeat = ingest(self.database, FIXTURE)
        self.assertEqual(before, state(self.database))
        self.assertEqual((repeat['inserted'], repeat['updated'], repeat['unchanged']), (0, 0, 10))
        other = connect(self.directory / 'other.sqlite3')
        try:
            initialize(other)
            ingest(other, FIXTURE)
            self.assertEqual(before, state(other))
        finally:
            other.close()
        ids = list(self.database.execute("SELECT id FROM authors WHERE canonical_name LIKE 'Alex Kim%'").fetchall())
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0][0], ids[1][0])
        self.assertTrue(all(row[0] < 2**53 for row in ids))

    def test_unchanged_ingestion_preserves_derived_edges_and_resolution(self):
        author_id = self.database.execute('SELECT id FROM authors ORDER BY id LIMIT 1').fetchone()[0]
        self.database.execute("INSERT INTO context_edges VALUES('edge','a','b','coauthorship',2018,'history/graph',1.0)")
        self.database.execute('INSERT INTO entity_resolution_matches VALUES(?,?,?,?,?)', ('observation', author_id, 1.0, 'matched', '{}'))
        self.database.commit()
        report = ingest(self.database, FIXTURE)
        self.assertEqual(report['unchanged'], 10)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM context_edges').fetchone()[0], 1)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM entity_resolution_matches').fetchone()[0], 1)

    def test_pid_identity_can_join_renames_and_separate_identical_names(self):
        file = self.directory / 'pids.xml'
        file.write_text('<dblp><article key="one"><author pid="p/1">Same Name</author><title>One</title><year>2018</year></article>'
                        '<article key="two"><author pid="p/2">Same Name</author><title>Two</title><year>2018</year></article>'
                        '<article key="three"><author pid="p/1">Renamed Person</author><title>Three</title><year>2024</year></article></dblp>')
        ingest(self.database, file)
        rows = self.database.execute("SELECT id FROM authors WHERE source_key LIKE 'dblp:pid:%'").fetchall()
        self.assertEqual(len(rows), 2)
        one = self.database.execute("SELECT author_id FROM paper_authors WHERE paper_id='one'").fetchone()[0]
        three = self.database.execute("SELECT author_id FROM paper_authors WHERE paper_id='three'").fetchone()[0]
        self.assertEqual(one, three)
        _, graph, _ = self.snapshot()
        self.assertEqual(graph.execute('SELECT canonical_name FROM authors WHERE id=?', (one,)).fetchone()[0], 'Same Name')

    def test_atomic_rollback_and_failed_run_survives(self):
        bad = self.directory / 'broken.xml'
        bad.write_text('<dblp><article key="new"><title>New</title><year>2020</year></article><article>')
        before = self.database.execute('SELECT COUNT(*) FROM papers').fetchone()[0]
        with self.assertRaises(ET.ParseError):
            ingest(self.database, bad)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM papers').fetchone()[0], before)
        run = self.database.execute('SELECT status,error FROM ingestion_runs ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(run['status'], 'failed')
        self.assertTrue(run['error'])
        self.assertFalse(tracemalloc.is_tracing())

    def test_updated_source_replaces_relationships_and_invalidates_edges(self):
        self.database.execute("INSERT INTO context_edges VALUES('edge','a','b','coauthorship',2018,'history/graph',1.0)")
        self.database.commit()
        corrected = self.directory / 'corrected.xml'
        corrected.write_text('<dblp><article key="history/graph"><author>Correct Person</author>'
                             '<title>Corrected paper</title><year>2017</year><journal>Correct Venue</journal></article></dblp>')
        report = ingest(self.database, corrected)
        self.assertEqual(report['updated'], 1)
        self.assertEqual(self.database.execute('SELECT COUNT(*) FROM context_edges').fetchone()[0], 0)
        names = self.database.execute("SELECT a.canonical_name FROM authors a JOIN paper_authors pa ON pa.author_id=a.id WHERE pa.paper_id='history/graph'").fetchall()
        self.assertEqual([row[0] for row in names], ['Correct Person'])
        self.assertEqual(self.database.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_snapshot_separates_all_periods_and_reports_newcomers(self):
        path, graph, manifest = self.snapshot()
        self.assertEqual(manifest['unknown_year_papers_excluded'], 1)
        self.assertEqual(manifest['papers_after_test_end_excluded'], 1)
        self.assertEqual(manifest['graph']['papers'], 4)
        self.assertEqual(manifest['labels']['test']['duplicate_titles_excluded'], 1)
        for split, year in [('train', 2020), ('validation', 2021), ('test', 2022)]:
            queries = load_queries(path / f'{split}_ground_truth.jsonl')
            self.assertEqual(len(queries), 1)
            self.assertEqual(queries[0].year, year)
            assert_no_leakage(graph, queries, [], CONFIG.graph_cutoff_year)
        self.assertEqual(manifest['labels']['train']['author_history_coverage'], 0.5)
        self.assertEqual(manifest['labels']['train']['query_history_coverage'], 1.0)
        self.assertIsNone(graph.execute("SELECT 1 FROM authors WHERE canonical_name='New Person'").fetchone())
        self.assertIsNone(graph.execute("SELECT 1 FROM venues WHERE name='Later Journal'").fetchone())
        with self.assertRaisesRegex(ValueError, 'immutable'):
            ingest(graph, FIXTURE)
        with self.assertRaisesRegex(ValueError, 'post-cutoff'):
            assert_no_leakage(self.database, [], [], CONFIG.graph_cutoff_year)

    def test_reproducible_labels_manifest_and_non_overwrite(self):
        first, _, manifest = self.snapshot('first')
        second, _, again = self.snapshot('second')
        self.assertEqual(manifest, again)
        for file in ('train_ground_truth.jsonl', 'validation_ground_truth.jsonl', 'test_ground_truth.jsonl'):
            self.assertEqual((first / file).read_bytes(), (second / file).read_bytes())
        with self.assertRaises(ValueError):
            write_split(self.database, first, CONFIG)
        for config in ((2020, 2019, 2021, 2022), (2019, 2020, 2020, 2022)):
            with self.assertRaises(ValueError):
                SplitConfig(*config)
        with self.assertRaisesRegex(ValueError, 'no usable queries'):
            write_split(self.database, self.directory / 'empty', SplitConfig(2019, 2020, 2023, 2024))
        self.assertFalse((self.directory / 'empty').exists())

    def test_noise_is_reproducible_per_observation_and_ground_truth_is_hidden(self):
        path, graph, _ = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            generate_noisy_authors(self.database, self.directory / 'bad.jsonl')
        a, b = path / 'noise.jsonl', path / 'repeat.jsonl'
        count = generate_noisy_authors(graph, a, seed=42, rate=1)
        generate_noisy_authors(graph, b, seed=42, rate=1)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        records = [json.loads(line) for line in a.read_text().splitlines()]
        truths = [json.loads(line) for line in a.with_suffix('.truth.jsonl').read_text().splitlines()]
        self.assertEqual(len(records), count)
        self.assertEqual(count, 4)
        self.assertEqual({row['record_id'] for row in records}, {row['record_id'] for row in truths})
        self.assertTrue(all('source_author_id' not in row and 'source_key' not in row and 'source_paper_id' not in row for row in records))
        self.assertTrue(all(max(row['observed_years']) <= 2019 for row in records))
        self.assertTrue(all('0001' not in row['noisy_name'] and '0002' not in row['noisy_name'] for row in records))
        self.assertLess(len({row['source_author_id'] for row in truths}), count)
        with self.assertRaises(ValueError):
            generate_noisy_authors(graph, a, rate=1)
        with self.assertRaises(ValueError):
            generate_noisy_authors(graph, path / 'invalid.jsonl', rate=1.1)

    def test_slice_reproducible_checksum_and_invalid_outputs(self):
        a, b = self.directory / 'a.xml', self.directory / 'b.xml'
        first = create_slice(FIXTURE, a, 3)
        create_slice(FIXTURE, b, 3)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(first['papers'], 3)
        self.assertEqual(first['output_sha256'], digest_file(a))
        checksum = self.directory / 'bad.md5'
        checksum.write_text('0' * 32)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            create_slice(FIXTURE, self.directory / 'bad.xml', 1, checksum=checksum)
        with self.assertRaisesRegex(ValueError, 'only'):
            create_slice(FIXTURE, self.directory / 'too-many.xml', 100)
        self.assertFalse((self.directory / 'too-many.xml').exists())

    def test_batch_isolated_validated_and_executable_from_other_directory(self):
        queries = self.directory / 'queries.txt'
        queries.write_text('graph\nno-matching-term\n\ngraph\n')
        output = self.directory / 'nested/results.json'
        run_batch(str(FIXTURE), str(queries), str(output))
        results = json.loads(output.read_text())
        validate_batch_results(results)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[1]['query'], 'no-matching-term')
        self.assertTrue(results[0]['results'][0]['evidence'][0]['collaborators'])
        other = self.directory / 'other.xml'
        other.write_text('<dblp><article key="different"><author>Different Person</author><title>graph</title></article></dblp>')
        subprocess.run([sys.executable, str(ROOT / 'run'), '--data', str(other), '--queries', str(queries), '--out', str(output)],
                       cwd=self.directory, check=True, capture_output=True)
        second = json.loads(output.read_text())
        self.assertEqual([item['name'] for item in second[0]['results']], ['Different Person'])
        with self.assertRaises(ValueError):
            run_batch(str(other), str(queries), str(other))
        second[0]['results'][0]['score'] = float('nan')
        with self.assertRaises(ValueError):
            validate_batch_results(second)

    def test_streaming_memory_does_not_grow_with_root_children(self):
        peaks = []
        for count in (2000, 40000):
            file = self.directory / f'memory-{count}.xml'
            with file.open('w') as stream:
                stream.write('<dblp>')
                for index in range(count):
                    stream.write(f'<article key="p{index}"><title>A <i>nested</i> paper</title><year>2020</year></article><ignored/>')
                stream.write('</dblp>')
            stats = {}
            tracemalloc.start()
            try:
                self.assertEqual(sum(1 for _ in iter_publications(file, stats)), count)
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
            self.assertEqual(stats['skipped_unsupported'], count)
        self.assertLess(peaks[1] - peaks[0], 2 * 1024 * 1024)

    def test_invalid_xml_root_and_year_fail_clearly(self):
        for text in ('<root/>', '<dblp><article key="x"><title>X</title><year>future</year></article></dblp>'):
            bad = self.directory / 'invalid.xml'
            bad.write_text(text)
            with self.assertRaises(ValueError):
                list(iter_publications(bad))


if __name__ == '__main__':
    unittest.main()
