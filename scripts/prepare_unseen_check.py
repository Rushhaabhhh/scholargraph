#!/usr/bin/env python3
"""Prepare a small, disjoint systems slice for the offline batch acceptance check."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, write_json
from hiresense.data.dblp import iter_publications
from hiresense.data.history import _serialize
from hiresense.db import connect

directory = Path('data/processed/unseen-systems-check')
if directory.exists():
    raise SystemExit('Use a fresh acceptance-check directory')
directory.mkdir(parents=True)
graph = connect('data/processed/history-enriched/source.sqlite3')
source = iter_publications('data/raw/dblp.xml.gz')
keys = []
try:
    with (directory / 'source.xml').open('wb') as output:
        output.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
        for paper in source:
            if (paper.year is None or not 2020 <= paper.year <= 2024 or not paper.authors
                    or not paper.key.startswith(('conf/osdi/', 'conf/sosp/'))):
                continue
            if graph.execute('SELECT 1 FROM papers WHERE id=?', (paper.key,)).fetchone():
                raise ValueError('Acceptance-check publication overlaps the model-development source')
            output.write(_serialize(paper))
            keys.append(paper.key)
            if len(keys) == 100:
                break
        output.write(b'</dblp>\n')
    if len(keys) != 100:
        raise ValueError('Insufficient distinct systems records')
    (directory / 'queries.txt').write_text('distributed storage crash recovery\n'
                                          'operating system memory management isolation\n'
                                          'fault tolerant distributed transactions\n')
    report = {'purpose': 'Disjoint-slice functional acceptance only, not ranking evaluation.',
              'papers': len(keys), 'years': [2020, 2024], 'prefixes': ['conf/osdi/', 'conf/sosp/'],
              'overlap_with_development_source': 0, 'source_sha256': digest_file(directory / 'source.xml'),
              'queries_sha256': digest_file(directory / 'queries.txt')}
    write_json(directory / 'manifest.json', report)
    print(json.dumps(report, indent=2))
finally:
    source.close()
    graph.close()
