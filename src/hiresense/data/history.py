"""Enrich a baseline with complete, predeclared historical venue families."""

import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from time import monotonic

from .artifacts import digest_file, package_digest, write_json
from .dblp import iter_publications


def _serialize(paper):
    element = ET.Element(paper.record_type, key=paper.key)
    for i, name in enumerate(paper.authors):
        pid = paper.author_pids[i] if paper.author_pids else None
        ET.SubElement(element, 'author', {'pid': pid} if pid else {}).text = name
    ET.SubElement(element, 'title').text = paper.title
    if paper.year is not None:
        ET.SubElement(element, 'year').text = str(paper.year)
    if paper.venue:
        ET.SubElement(element, 'journal' if paper.record_type == 'article' else 'booktitle').text = paper.venue
    return ET.tostring(element, encoding='utf-8') + b'\n'


def enrich_history(config_path, output):
    config_path, output = Path(config_path), Path(output)
    config = json.loads(config_path.read_text())
    manifest_path = output.with_suffix(output.suffix + '.manifest.json')
    if output.exists() or manifest_path.exists():
        raise ValueError('Use new enriched source and manifest paths')
    lower, cutoff = config['min_year'], config['cutoff_year']
    prefixes = tuple(config['key_prefixes'])
    if not 1 <= lower <= cutoff <= 9999 or not prefixes or any(not p.endswith('/') for p in prefixes):
        raise ValueError('Require valid historical years and complete DBLP key prefixes ending in /')
    archive, baseline = Path(config['archive']), Path(config['baseline'])
    if output.resolve() in {archive.resolve(), baseline.resolve()}:
        raise ValueError('Output must not replace either input')
    source_hash, baseline_hash = digest_file(archive), digest_file(baseline)
    expected = Path(config['checksum']).read_text().split()[0].lower()
    actual = digest_file(archive, 'md5')
    if actual != expected:
        raise ValueError('Raw DBLP MD5 checksum mismatch')
    started, code_start = monotonic(), package_digest()
    seen, years, types, venues = set(), Counter(), Counter(), Counter()
    added = baseline_count = scanned = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix='.history-', suffix='.xml')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
            for paper in iter_publications(baseline):
                if paper.key in seen:
                    raise ValueError('Baseline contains duplicate publication keys')
                seen.add(paper.key)
                stream.write(_serialize(paper))
                baseline_count += 1
            for paper in iter_publications(archive):
                scanned += 1
                if scanned % 500000 == 0:
                    print(f'History scan: {scanned:,} records; {added:,} added; {monotonic()-started:.0f}s',
                          file=sys.stderr, flush=True)
                if (paper.year is None or not lower <= paper.year <= cutoff or not paper.authors
                        or paper.record_type not in ('article', 'inproceedings')
                        or not paper.key.startswith(prefixes) or paper.key in seen):
                    continue
                seen.add(paper.key)
                stream.write(_serialize(paper))
                added += 1
                years[paper.year] += 1
                types[paper.record_type] += 1
                venues[paper.venue or '(unknown)'] += 1
            stream.write(b'</dblp>\n')
        if not added:
            raise ValueError('No new historical papers matched the declared selection')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    code_end = package_digest()
    report = {'source': 'DBLP', 'license': 'CC0', 'config': config, 'config_sha256': digest_file(config_path),
              'raw_sha256': source_hash, 'verified_md5': actual, 'baseline_sha256': baseline_hash,
              'baseline_papers': baseline_count, 'added_historical_papers': added,
              'total_papers': len(seen), 'records_scanned': scanned,
              'added_year_counts': dict(sorted(years.items())), 'added_record_types': dict(types),
              'added_venue_counts': dict(venues), 'output_sha256': digest_file(output),
              'elapsed_seconds': round(monotonic()-started, 3),
              'package_source_sha256_start': code_start, 'package_source_sha256_end': code_end,
              'package_changed_during_run': code_start != code_end,
              'selection_module_sha256': digest_file(__file__),
              'limitation': 'Purposeful ML/IR venue-family history, not a representative sample of all DBLP. '
                            'Future records and target-author identities never select additional history.'}
    write_json(manifest_path, report)
    return report
