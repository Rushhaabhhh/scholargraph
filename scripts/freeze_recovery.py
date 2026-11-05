#!/usr/bin/env python3
"""Seal validation-selected recovery models and untouched test provenance."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,package_digest,write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--training-report',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--allow-missed-goals',action='store_true',help='Freeze only after reviewing missed validation goals; recorded in freeze')
a=p.parse_args()
if a.out.exists():raise ValueError('Use a new freeze path')
r=json.loads(a.training_report.read_text());config=r['config'];code=package_digest()
if r['scope']!='Train/validation selection only; reserved test not opened.' or not r['package_source_sha256_start']==r['package_source_sha256_end']==code:
    raise ValueError('Training code/protocol differs from current package')
if r['runner_sha256']!=digest_file(Path(__file__).with_name('train_recovery.py')) or r['adapter_runner_sha256']!=digest_file(Path(__file__).with_name('train_query_adapters.py')):
    raise ValueError('Training entrypoints changed since selection')
d=r['diagnostics']
gates={'candidate_recall_known':d['candidate_recall_known']>=.5,'query_candidate_success':d['query_candidate_success']>=.5,
       'ndcg_at_10':d['metrics']['ndcg_at_10']>=.10,'mrr':d['metrics']['mrr']>=.15}
if not all(gates.values()) and not a.allow_missed_goals:
    raise ValueError('Initial validation goals missed; inspect the validation report before deliberate freezing with --allow-missed-goals. Test has not been opened.')
selected=Path(r['selected_model'])
if digest_file(selected)!=r['selected_model_sha256']:raise ValueError('Selected model changed')
models={}
for name in ('selected','reference','full','without_cross','without_graph','without_author_features'):
    path=selected.parent/f'{name}.json';models[name]={'path':str(path),'sha256':digest_file(path)}
    model=json.loads(path.read_text())
    if model['validation_labels_sha256']!=json.loads(selected.read_text())['validation_labels_sha256']:
        raise ValueError('Models did not share validation labels')
test=Path(config['source_work'])/'test';manifest=json.loads((test/'manifest.json').read_text())
if manifest['window']['role']!='test' or digest_file(test/'labels.jsonl')!=manifest['labels_sha256']:
    raise ValueError('Reserved test labels differ from plan')
index=json.loads((test/'index/manifest.json').read_text())
regression=Path('data/processed/reserved-rolling-v1/test_ground_truth.jsonl')
write_json(a.out,{'validation_goals_met':gates,'missed_goals_reviewed':a.allow_missed_goals,'protocol':'rolling-recovery-v2','package_source_sha256':code,'selected':r['selected'],
    'runner_files_sha256':{str(Path('scripts')/name):digest_file(Path(__file__).with_name(name)) for name in ('train_recovery.py','train_query_adapters.py','evaluate_recovery.py')},
    'training_report':str(a.training_report),'training_report_sha256':digest_file(a.training_report),
    'config':config,'retrieval':r['selected_settings'],'models':models,
    'test_directory':str(test),'test_manifest_sha256':digest_file(test/'manifest.json'),
    'test_labels_sha256':manifest['labels_sha256'],'inference_content_sha256':index['content_sha256'],
    'regression_labels':str(regression),'regression_labels_sha256':digest_file(regression),
    'previous_model':{'path':'models/baselines/hybrid_ranker_v1.json','sha256':digest_file('models/baselines/hybrid_ranker_v1.json')},
    'previous_cache':'data/processed/hybrid-final-v1/features-reserved-test',
    'scope':'Fresh query keys/titles excluded from previous evaluation files; declared venue-portfolio chronology, not independent human relevance. Regression cohort was previously inspected and cannot select models.'})
print(json.dumps({'freeze':str(a.out),'sha256':digest_file(a.out),'selected':r['selected']},indent=2))
