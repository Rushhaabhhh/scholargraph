"""Create a reproducible, bounded development slice without a network or DTD."""

import os
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from time import monotonic

from ..contracts import CONTRACT_VERSION
from .artifacts import digest_file, write_json
from .dblp import PUBLICATION_TAGS, iter_publications


def create_slice(source: str | Path, output: str | Path, limit: int,
                 min_year: int = 1, max_year: int = 9999,
                 record_types: tuple[str, ...] = ('article', 'inproceedings', 'incollection'),
                 checksum: str | Path | None = None) -> dict:
    if limit < 1 or not 1 <= min_year <= max_year <= 9999:
        raise ValueError('Require a positive limit and 1 <= min year <= max year <= 9999')
    if not record_types or not set(record_types) <= PUBLICATION_TAGS:
        raise ValueError('Unknown or empty DBLP record types')
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or output.exists() or output.with_suffix(output.suffix + '.manifest.json').exists():
        raise ValueError('Slice output must be a new path distinct from its source')
    started = monotonic()
    source_hash = digest_file(source)
    verified_md5 = None
    if checksum:
        expected = Path(checksum).read_text().split()[0].lower()
        verified_md5 = digest_file(source, 'md5')
        if expected != verified_md5:
            raise ValueError(f'DBLP checksum mismatch: expected {expected}, got {verified_md5}')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix='.slice-', suffix='.xml')
    years, kinds, seen_keys = Counter(), Counter(), set()
    scanned = 0
    parse_stats = {}
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<dblp>\n')
            publications = iter_publications(source, parse_stats)
            try:
                for paper in publications:
                    scanned += 1
                    if (paper.record_type not in record_types or not paper.authors or paper.year is None
                            or not min_year <= paper.year <= max_year or paper.key in seen_keys):
                        continue
                    seen_keys.add(paper.key)
                    element = ET.Element(paper.record_type, key=paper.key)
                    for index, name in enumerate(paper.authors):
                        pid = paper.author_pids[index] if paper.author_pids else None
                        ET.SubElement(element, 'author', {'pid': pid} if pid else {}).text = name
                    ET.SubElement(element, 'title').text = paper.title
                    ET.SubElement(element, 'year').text = str(paper.year)
                    if paper.venue:
                        ET.SubElement(element, 'journal' if paper.record_type == 'article' else 'booktitle').text = paper.venue
                    stream.write(ET.tostring(element, encoding='utf-8') + b'\n')
                    years[paper.year] += 1
                    kinds[paper.record_type] += 1
                    if len(seen_keys) == limit:
                        break
            finally:
                publications.close()
            stream.write(b'</dblp>\n')
        if len(seen_keys) != limit:
            raise ValueError(f'Source contained only {len(seen_keys)} matching papers; requested {limit}')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    manifest = {
        'contract_version': CONTRACT_VERSION, 'source': 'DBLP', 'license': 'CC0',
        'source_sha256': source_hash, 'verified_md5': verified_md5,
        'output_sha256': digest_file(output), 'records_scanned': scanned, 'parser': parse_stats, 'papers': len(seen_keys),
        'selection': {'strategy': 'first_matching_unique_records_in_source_order', 'limit': limit,
                      'min_year': min_year, 'max_year': max_year, 'record_types': list(record_types),
                      'require_authors': True, 'require_year': True},
        'sampling_limitation': 'Source-order slice is not a representative random sample of all research.',
        'year_counts': dict(sorted(years.items())), 'record_type_counts': dict(sorted(kinds.items())),
        'elapsed_seconds': round(monotonic() - started, 3),
    }
    write_json(output.with_suffix(output.suffix + '.manifest.json'), manifest)
    return manifest
