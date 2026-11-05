#!/usr/bin/env python3
"""Evaluate a frozen recovery model once, including the old fixed regression cohort."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from time import monotonic

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,package_digest,write_json
from hiresense.db import connect
from hiresense.evaluation.features import materialize
from hiresense.evaluation.recovery import load_window,discovery_diagnostics
from hiresense.evaluation.ranking import evaluate_rankings
from hiresense.evaluation.split import load_queries,assert_no_leakage
from hiresense.ranking.service import search
from hiresense.ranking.scoring import score_model
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.evidence import EvidenceIndex
from hiresense.assistant.grounding import GroundingVerifier
from hiresense.api.runtime import Backend
from hiresense.assistant.memory import SessionStore


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise ValueError('Use a new final report path')
    started=monotonic();f=json.loads(a.freeze.read_text())
    if package_digest()!=f['package_source_sha256'] or digest_file(f['training_report'])!=f['training_report_sha256']:
        raise ValueError('Frozen training report or source code changed')
    if any(digest_file(path)!=sha for path,sha in f['runner_files_sha256'].items()):
        raise ValueError('Frozen experiment entrypoints changed')
    models={}
    for name,item in f['models'].items():
        if digest_file(item['path'])!=item['sha256']:raise ValueError('Frozen model changed')
        models['learned' if name=='selected' else name]=json.loads(Path(item['path']).read_text())
    directory=Path(f['test_directory']);config=f['config']
    if digest_file(directory/'manifest.json')!=f['test_manifest_sha256']:raise ValueError('Test manifest changed')
    db=connect(directory/'graph.sqlite3');engine=None
    try:
        queries,sha=load_window(directory,db)
        encoder=LocalEncoder(config['encoder']);cross=CrossEncoder(config['cross_encoder'])
        if any(m['encoder_sha256'] != encoder.signature or m['cross_encoder_sha256'] != cross.signature for m in models.values()):
            raise ValueError('Frozen models and local neural artifacts differ')
        engine=EvidenceIndex(db,directory/'index',encoder,profiles=directory/'evidence_profiles',cross_encoder=cross,query_adapter=models['learned'].get('query_adapter'),**f['retrieval'])
        if sha!=f['test_labels_sha256'] or engine.manifest['content_sha256']!=f['inference_content_sha256']:
            raise ValueError('Frozen inference evidence/labels changed')
        work=Path(config['work'])
        cache=materialize(engine,queries,work/'features-final',sha)
        evaluation=evaluate_rankings(engine,cache,models)
        diagnostics=discovery_diagnostics(cache,set(engine.authors),models['learned'],engine.author_papers)
        regression_file=Path(f['regression_labels'])
        if digest_file(regression_file)!=f['regression_labels_sha256']:raise ValueError('Regression labels changed')
        regression_queries=load_queries(regression_file)
        assert_no_leakage(db,[],regression_queries,engine.anchor_year)
        regression_cache=materialize(engine,regression_queries,work/'features-v1-regression',digest_file(regression_file))
        regression={'scope':'Previously inspected fixed v1 cohort; no model selection. Expanded graph/retrieval/model change together.',
            'evaluation':evaluate_rankings(engine,regression_cache,{'learned':models['learned']}),
            'diagnostics':discovery_diagnostics(regression_cache,set(engine.authors),models['learned'],engine.author_papers)}
        previous=f['previous_model'];previous_directory=Path(f['previous_cache'])
        old_manifest=json.loads((previous_directory/'manifest.json').read_text())
        if digest_file(previous['path'])!=previous['sha256'] or old_manifest['signature']['labels_sha256']!=digest_file(regression_file) or digest_file(previous_directory/'features.npz')!=old_manifest['features_sha256']:
            raise ValueError('Previous-system regression model/cache changed')
        old_model=json.loads(Path(previous['path']).read_text())
        with np.load(previous_directory/'features.npz',allow_pickle=False) as old:
            old_scores=score_model(old['features'],old_model)
            new_scores=score_model(regression_cache['features'],models['learned'])
            paired=[]
            for i,q in enumerate(regression_queries):
                x,y=old['offsets'][i:i+2];ids=old['author_ids'][x:y]
                old_rank=ids[np.lexsort((ids,-old_scores[x:y]))].tolist()[:400]
                x,y=regression_cache['offsets'][i:i+2];ids=regression_cache['author_ids'][x:y]
                new_rank=ids[np.lexsort((ids,-new_scores[x:y]))].tolist()[:400]
                paired.append((ranking_metrics(old_rank,set(q.relevant_author_ids)),ranking_metrics(new_rank,set(q.relevant_author_ids))))
            random=np.random.default_rng(config['seed']);indices=random.integers(0,len(paired),size=(1000,len(paired)))
            comparison={}
            for metric in ('ndcg_at_10','mrr'):
                before=np.asarray([r[0][metric] for r in paired]);after=np.asarray([r[1][metric] for r in paired]);delta=after-before
                comparison[metric]={'previous':float(before.mean()),'new':float(after.mean()),'delta':float(delta.mean()),
                                    'paired_bootstrap_95pct':np.quantile(delta[indices].mean(axis=1),[.025,.975]).tolist()}
            regression['paired_previous_system']={'metrics':comparison,'mrr_scope':'Both lists capped at 400 authors.',
                'scope':'Identical old regression queries; expanded source, retrieval and learned model change together.'}
        # Time the selected deployment policy, not an ablation's extra model work.
        if not models['learned'].get('use_cross_encoder',True):engine.cross_encoder=None
        verifier=GroundingVerifier(db);timings=[];claims=unsupported=0
        for q in queries[:20]:
            begin=monotonic();results=verifier.explain(search(engine,q.text,models['learned']))
            timings.append((monotonic()-begin)*1000)
            for person in results:
                for claim in person['claims']:claims+=1;unsupported+=not claim['supported']
        api_rows=[]
        with tempfile.TemporaryDirectory() as tmp:
            backend=Backend(db,engine,models['learned'],SessionStore(Path(tmp)/'sessions.sqlite3',engine.manifest['content_sha256']))
            for q in queries[:20]:
                packet=backend.search({'query':q.text})
                api_rows.append({'query_id':q.query_id,'query':q.text,'retrieval_query':packet['retrieval_query'],
                    'effective_filters':packet['effective_filters'],'provider':packet['understanding']['provider'],
                    'hit_at_10':bool(set(q.relevant_author_ids)&{r['person_id'] for r in packet['results']})})
        goals={'candidate_recall_known':diagnostics['candidate_recall_known']>=.5,
               'query_candidate_success':diagnostics['query_candidate_success']>=.5,
               'ndcg_at_10':diagnostics['metrics']['ndcg_at_10']>=.10,'mrr':diagnostics['metrics']['mrr']>=.15}
        if package_digest()!=f['package_source_sha256']:raise ValueError('Code changed during frozen final evaluation')
        write_json(a.out,{'command':sys.argv,'freeze_sha256':digest_file(a.freeze),'protocol':f['protocol'],'scope':f['scope'],
            'selected':f['selected'],'package_source_sha256':package_digest(),'evaluation':evaluation,'diagnostics':diagnostics,
            'regression':regression,'initial_goals_met':goals,'latency':{'p50_ms':float(np.median(timings)),
            'p95_ms':float(np.quantile(timings,.95)),'samples':len(timings),'scope':'Sequential warm selected-model search and grounded evidence; no throughput claim.'},
            'grounding_sample':{'claims':claims,'unsupported':unsupported},'api_query_sample':api_rows,
            'elapsed_seconds':round(monotonic()-started,3),
            'limitations':['Automatic future authorship is weak/incomplete expert relevance.','Venue-portfolio sample is not random or independently human judged.','Pretraining overlap cannot be ruled out.','Final scores may miss proposed goals; no test-based tuning permitted.']})
        print(json.dumps({'report':str(a.out),'diagnostics':diagnostics,'goals':goals},indent=2))
    finally:
        if engine:engine.close()
        db.close()

if __name__=='__main__':main()
