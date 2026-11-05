#!/usr/bin/env python3
"""Resume the authorized recovery experiment with persisted progress and strict reports."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from hiresense.data.artifacts import package_digest,write_json

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--wait-for-preparation',action='store_true')
p.add_argument('--use-prepared-validation',action='store_true',help='Allow training while the final graph finishes')
p.add_argument('--state-name',default='run-state.json')
a=p.parse_args()
work=ROOT/'data/processed/recovery-training-v2';work.mkdir(parents=True,exist_ok=True)
state=work/a.state_name;began=time.monotonic();code=package_digest()

def status(phase,**extra):
    write_json(state,{'phase':phase,'updated_at_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds_this_invocation':round(time.monotonic()-began,2),'package_source_sha256':code,**extra})

try:
    preparation=ROOT/'data/processed/recovery-v2/preparation.json'
    if a.wait_for_preparation:
        status('waiting_for_graph_and_index_preparation')
        limit=time.monotonic()+7200
        while not preparation.exists():
            if time.monotonic()>limit:raise TimeoutError('Preparation did not finish within two hours; inspect preparation logs')
            time.sleep(5)
    if not preparation.exists() and not a.use_prepared_validation:raise ValueError('Run prepare_recovery.py first')
    if a.use_prepared_validation:
        for role in ('train-early','train-later','validation'):
            if not (ROOT/'data/processed/recovery-v2'/role/'index/manifest.json').exists():
                raise ValueError('Training/validation indexes are incomplete')
    steps=[('seal_portfolio_cohort','data/processed/recovery-v2/cohort-preparation.json',
            ['scripts/prepare_recovery_cohort.py','--config','experiments/recovery-cohort-v2.json']),
           ('train_and_select','results/recovery-validation-v2.json',
            ['scripts/train_recovery.py','--config','experiments/recovery-training-v2.json']),
           ('freeze','experiments/recovery-freeze-v2.json',
            ['scripts/freeze_recovery.py','--training-report','results/recovery-validation-v2.json','--out','experiments/recovery-freeze-v2.json']),
           ('final_evaluation','results/recovery-final-v2.json',
            ['scripts/evaluate_recovery.py','--freeze','experiments/recovery-freeze-v2.json','--out','results/recovery-final-v2.json'])]
    for phase,output,command in steps:
        if package_digest()!=code:raise ValueError('Runtime code changed after this invocation began; inspect before resuming')
        if (ROOT/output).exists():
            print(f'Existing {phase} report retained: {output}',flush=True)
            continue
        status(phase,command=[sys.executable,*command],expected_report=output)
        print(f'Starting {phase}',flush=True)
        subprocess.run([sys.executable,*command],cwd=ROOT,check=True)
        if not (ROOT/output).exists():raise RuntimeError(f'{phase} completed without its expected report')
    status('evaluation_complete_integration_pending',report='results/recovery-final-v2.json')
except BaseException as error:
    status('failed',error_type=type(error).__name__,message=str(error))
    raise
