"""Seeded noisy authorship observations, with ground truth in a separate file."""

import hashlib
import json
import random
import re
import unicodedata
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ..contracts import CONTRACT_VERSION
from ..models import NoisyAuthorRecord
from .artifacts import digest_file, write_json

_SUFFIX = re.compile(r'\s+\d{4,}$')


def visible_name(name: str) -> str:
    # DBLP's disambiguation suffix is an answer label, not a noisy name feature.
    return _SUFFIX.sub('', name)


def corrupt_name(name: str, corruption: str, rng: random.Random) -> str:
    name = visible_name(name)
    parts = name.split()
    if corruption == 'initials' and len(parts) > 1:
        result = ' '.join([part[0] + '.' for part in parts[:-1]] + [parts[-1]])
    elif corruption == 'name_order' and len(parts) > 1:
        result = ' '.join(reversed(parts))
    elif corruption == 'transliteration':
        result = ''.join(char for char in unicodedata.normalize('NFKD', name) if not unicodedata.combining(char))
    else:
        result = name
    if result == name:
        positions = [i for i, char in enumerate(name) if char.isalpha()]
        index = rng.choice(positions) if positions else 0
        result = name[:index] + name[index + 1:] if len(name) > 1 else name + 'x'
    return result.strip() or name + 'x'


def generate_noisy_authors(database, output_path: str | Path, seed: int = 42, rate: float = 0.25) -> int:
    if not 0 <= rate <= 1:
        raise ValueError('Noise observation sampling rate must be between 0 and 1')
    cutoff = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if cutoff is None:
        raise ValueError('Generate noise from a prepared graph snapshot, not the all-period source database')
    output = Path(output_path)
    truth_path = output.with_suffix('.truth.jsonl')
    manifest_path = output.with_suffix('.manifest.json')
    if any(path.exists() for path in (output, truth_path, manifest_path)):
        raise ValueError('Noise outputs must be new paths')
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    count, kinds = 0, Counter()
    try:
        with output.open('w', encoding='utf-8') as observations, truth_path.open('w', encoding='utf-8') as truth:
            for paper in database.execute('SELECT id,year,venue FROM papers ORDER BY id'):
                authors = database.execute('''SELECT pa.author_id,pa.author_position,pa.observed_name,a.source_key
                    FROM paper_authors pa JOIN authors a ON a.id=pa.author_id
                    WHERE pa.paper_id=? ORDER BY pa.author_position''', (paper['id'],)).fetchall()
                for author in authors:
                    if rng.random() >= rate:
                        continue
                    corruption = rng.choice(('initials', 'name_order', 'typo', 'transliteration'))
                    noisy_name = corrupt_name(author['observed_name'], corruption, rng)
                    record_id = hashlib.sha256(f"{seed}:{paper['id']}:{author['author_position']}".encode()).hexdigest()[:24]
                    coauthors = tuple(visible_name(other['observed_name']) for other in authors
                                      if other['author_id'] != author['author_id'] and rng.random() >= 0.15)
                    record = NoisyAuthorRecord(
                        record_id=record_id, noisy_name=noisy_name,
                        observed_years=(paper['year'],), observed_coauthors=coauthors,
                        observed_venues=(paper['venue'],) if paper['venue'] else (),
                        corruptions=(corruption,),
                    )
                    observations.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + '\n')
                    truth.write(json.dumps({'record_id': record_id, 'source_author_id': author['author_id'],
                                            'source_key': author['source_key'], 'source_paper_id': paper['id']},
                                           ensure_ascii=False, sort_keys=True) + '\n')
                    kinds[corruption] += 1
                    count += 1
        write_json(manifest_path, {
            'contract_version': CONTRACT_VERSION, 'seed': seed, 'sampling_rate': rate,
            'graph_cutoff_year': int(cutoff[0]), 'records': count, 'corruption_counts': dict(kinds),
            'observation_unit': 'paper authorship; an identity may have several independent observations',
            'truth_policy': 'The .truth.jsonl file is evaluator-only; never pass it as matcher features.',
            'files': {output.name: digest_file(output), truth_path.name: digest_file(truth_path)},
        })
        return count
    except BaseException:
        for path in (output, truth_path, manifest_path):
            path.unlink(missing_ok=True)
        raise
