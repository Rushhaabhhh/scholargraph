"""Keep a fixed validation/test cohort while enriching only historical evidence."""
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from ..data.artifacts import digest_file, title_key, write_json
from .features import load_partition
from .pilot import _sample
from .split import assert_no_leakage, load_queries


def transfer_cohort(parent_pilot, expanded_dataset, graph, output, train_count=3000, seed=42):
    parent_pilot, expanded_dataset, output = map(Path, (parent_pilot, expanded_dataset, output))
    if output.exists():
        raise ValueError('Use a new transferred cohort path')
    parent = json.loads((parent_pilot / 'manifest.json').read_text())
    expanded = json.loads((expanded_dataset / 'manifest.json').read_text())
    if parent['split'] != expanded['split']:
        raise ValueError('Historical cutoff and label periods must remain identical')
    all_train, _ = load_partition(expanded_dataset, 'train', graph)
    selected = {'train': _sample(all_train, train_count, seed, 'train')}
    removed = {}
    for role in ('validation', 'test'):
        file = parent_pilot / f'{role}_ground_truth.jsonl'
        if digest_file(file) != parent['files'][file.name]:
            raise ValueError('Parent pilot labels differ from their sealed manifest')
        queries = load_queries(file)
        selected[role] = [q for q in queries if not graph.execute(
            'SELECT 1 FROM papers WHERE id=? OR title_key=? LIMIT 1',
            (q.source_paper_id, title_key(q.text))).fetchone()]
        removed[role] = len(queries) - len(selected[role])
        if not selected[role]:
            raise ValueError('No clean transferred evaluation queries remain')
    assert_no_leakage(graph, selected['train'], selected['validation'] + selected['test'],
                      parent['split']['graph_cutoff_year'])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output.parent, prefix='.transfer-'))
    try:
        files = {}
        for role, queries in selected.items():
            path = stage / f'{role}_ground_truth.jsonl'
            with path.open('w', encoding='utf-8') as stream:
                for q in queries:
                    stream.write(json.dumps(asdict(q), ensure_ascii=False, sort_keys=True) + '\n')
            files[path.name] = digest_file(path)
        manifest = {'contract_version': 1, 'source_dataset_sha256': expanded['source_dataset_sha256'],
                    'split': expanded['split'], 'files': files,
                    'parent_pilot_manifest_sha256': digest_file(parent_pilot / 'manifest.json'),
                    'counts': {role: len(queries) for role, queries in selected.items()},
                    'excluded_for_new_history_title_or_key_overlap': removed,
                    'seed': seed, 'protocol': 'Expanded history; fixed parent validation/test with mechanical leakage exclusions.',
                    'limitation': parent['limitation'], 'parent_selection': parent['selection']}
        write_json(stage / 'manifest.json', manifest)
        stage.rename(output)
        return manifest
    except BaseException:
        shutil.rmtree(stage)
        raise
