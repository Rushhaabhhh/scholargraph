#!/usr/bin/env python3
"""Validation-only recovery experiments on rolling historical snapshots."""
import argparse
import gc
import json
import platform
import sys
from pathlib import Path
from time import monotonic

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.features import materialize
from hiresense.evaluation.recovery import load_window, merge_training, discovery_diagnostics
from hiresense.evaluation.ranking import evaluate_rankings, name_counterfactual
from hiresense.ranking.lambdamart import train_lambdamart
from hiresense.ranking.scoring import train_ranker
from hiresense.retrieval.crossencoder import CrossEncoder
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.evidence import EvidenceIndex,EVIDENCE_FEATURES
from hiresense.retrieval.index import FEATURE_NAMES
from hiresense.retrieval.adaptation import QueryAdapter
from train_query_adapters import train_adapters


def open_engine(config,role,settings,cross):
    directory=Path(config['source_work'])/role
    database=connect(directory/'graph.sqlite3')
    encoder=LocalEncoder(config['encoder'])
    try:
        engine=EvidenceIndex(database,directory/'index',encoder,profiles=directory/'evidence_profiles',
                             cross_encoder=cross,query_adapter=config.get('_query_adapter'),**settings)
        return database,engine
    except BaseException:
        database.close();raise


def pilot(config,adapters):
    file=Path(config['retrieval_report'])
    if file.exists():
        report=json.loads(file.read_text())
        if report['package_source_sha256']!=package_digest() or report['config_sha256']!=digest_file(config['_config_file']) or report.get('runner_sha256')!=digest_file(__file__):
            raise ValueError('Retrieval pilot does not match current code/config')
        directory=Path(config['source_work'])/config['validation_role']
        if digest_file(directory/'labels.jsonl')!=report['validation_labels_sha256'] or json.loads((directory/'index/manifest.json').read_text())['content_sha256']!=report['validation_content_sha256']:
            raise ValueError('Retrieval pilot validation data changed')
        return report['selected_settings'],report.get('selected_adapter_file')
    settings=dict(config['retrieval'])
    db,engine=open_engine(config,config['validation_role'],settings,None)
    try:
        queries,sha=load_window(Path(config['source_work'])/config['validation_role'],db)
        queries=queries[:200]
        vectors=engine.encoder.encode([q.text for q in queries])
        variants=[('paper-400',dict(paper_limit=512,candidate_limit=400,profile_limit=0,author_lexical_limit=0,expansion_limit=0)),
                  ('paper-1200',dict(paper_limit=1536,candidate_limit=1200,profile_limit=0,author_lexical_limit=0,expansion_limit=0)),
                  ('evidence-800',dict(paper_limit=1024,candidate_limit=800,profile_limit=256,author_lexical_limit=256,expansion_limit=64)),
                  ('evidence-1200',dict()),
                  ('without-graph',dict(expansion_limit=0)),
                  ('without-profiles',dict(profile_limit=0)),
                  ('without-author-lexical',dict(author_lexical_limit=0))]
        variants=[(name,changes,None) for name,changes in variants]
        variants += [(item['name'],{},item['path']) for item in adapters]
        reports=[]
        for name,changes,adapter_file in variants:
            adapter=json.loads(Path(adapter_file).read_text()) if adapter_file else None
            engine.query_adapter=QueryAdapter(adapter,engine.encoder.dimensions) if adapter else None
            actual={**settings,**changes}
            for k,v in actual.items():setattr(engine,k,v)
            offsets=[0];ids=[];features=[];latencies=[]
            for q,vector in zip(queries,vectors):
                started=monotonic();r=engine.retrieve(q.text,vector)
                latencies.append((monotonic()-started)*1000)
                ids.extend(r['author_ids']);features.append(r['features']);offsets.append(len(ids))
            cache={'queries':queries,'author_ids':np.asarray(ids),'features':np.concatenate(features),'offsets':np.asarray(offsets)}
            report=discovery_diagnostics(cache,set(engine.authors))
            reports.append({'name':name,'settings':actual,'adapter_file':adapter_file,'diagnostics':report,
                'latency_ms':{'p50':float(np.median(latencies)),'p95':float(np.quantile(latencies,.95))},
                'latency_scope':'Feature computation with cached query vectors and cross-encoder disabled; not end-to-end serving latency.'})
            print('Retrieval pilot',name,report['candidate_recall_known'],report['query_candidate_success'],flush=True)
        chosen=max(reports,key=lambda r:(r['diagnostics']['candidate_recall_known'],
            r['diagnostics']['query_candidate_success'],-r['settings']['candidate_limit']))
        write_json(file,{'scope':'Validation-only, deterministic first 200 round-robin selected queries; no test opened.',
            'config_sha256':digest_file(config['_config_file']),'package_source_sha256':package_digest(),
            'validation_labels_sha256':sha,'validation_content_sha256':engine.manifest['content_sha256'],
            'selection':config['selection'],'runner_sha256':digest_file(__file__),
            'selected':chosen['name'],'selected_settings':chosen['settings'],
            'selected_adapter_file':chosen['adapter_file'],'comparisons':reports})
        return chosen['settings'],chosen['adapter_file']
    finally:engine.close();db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args();config=json.loads(args.config.read_text());config['_config_file']=str(args.config)
    out=Path(config['report'])
    if out.exists():raise ValueError('Use a fresh report/config')
    if 'cohort_report' in config:
        cohort=json.loads(Path(config['cohort_report']).read_text())
        for role,item in cohort['windows'].items():
            actual=json.loads((Path(config['source_work'])/role/'manifest.json').read_text())
            if actual != item: raise ValueError('Cohort manifest changed after sealing')
    started=monotonic();code=package_digest();adapters=train_adapters(config)
    settings,adapter_file=pilot(config,adapters)
    config['_query_adapter']=json.loads(Path(adapter_file).read_text()) if adapter_file else None
    work=Path(config['work']);models_dir=work/'models';models_dir.mkdir(parents=True,exist_ok=True)
    cross=CrossEncoder(config['cross_encoder']);parts=[];windows=[]
    for role in config['train_roles']:
        db,engine=open_engine(config,role,settings,cross)
        try:
            queries,sha=load_window(Path(config['source_work'])/role,db)
            cache=materialize(engine,queries,work/f'features-{role}',sha);parts.append(cache)
            windows.append({'role':role,'cutoff_year':engine.anchor_year,'content_sha256':engine.manifest['content_sha256'],
                            'labels_sha256':sha,'queries':len(queries)})
        finally:engine.close();db.close();del engine;gc.collect()
    del cache
    training=merge_training(parts);del parts;gc.collect()
    db,engine=open_engine(config,config['validation_role'],settings,cross)
    try:
        queries,sha=load_window(Path(config['source_work'])/config['validation_role'],db)
        validation=materialize(engine,queries,work/'features-validation',sha)
        train_sha=__import__('hashlib').sha256(json.dumps(windows,sort_keys=True).encode()).hexdigest()
        metadata={'encoder_sha256':engine.encoder.signature,'cross_encoder_sha256':cross.signature,
            'training_content_sha256':train_sha,'train_labels_sha256':train_sha,'training_windows':windows,
            'validation_labels_sha256':sha,'graph_cutoff_year':max(w['cutoff_year'] for w in windows),
            'validation_graph_cutoff_year':engine.anchor_year,'retrieval_kind':'evidence','retrieval':settings,
            'use_cross_encoder':True,'package_source_sha256':code,'query_adapter':config['_query_adapter']}
        models={};reports={}
        path=models_dir/'reference.json'
        reports['reference']=train_ranker({**training,'features':training['features'][:,:len(FEATURE_NAMES)]},
            {**validation,'features':validation['features'][:,:len(FEATURE_NAMES)]},path,
            {**metadata,'retrieval_kind':'evidence','use_cross_encoder':False},seed=config['seed'],hard_negatives=48,tail_negatives=16)
        models['reference']=json.loads(path.read_text())
        path=models_dir/'full.json'
        reports['full']=train_lambdamart(training,validation,path,metadata,seed=config['seed'],feature_names=EVIDENCE_FEATURES,
            settings=[{'n_estimators':80,'num_leaves':7},{'n_estimators':160,'num_leaves':15},{'n_estimators':320,'num_leaves':15}])
        models['full']=json.loads(path.read_text())
        ablations={'without_cross':('cross_max','cross_top2','cross_observed','cross_logit_max','cross_logit_mean','cross_scored_fraction'),
                   'without_graph':('graph_support','log_collaborators'),
                   'without_author_features':('author_lexical_max','author_lexical_rank','profile_similarity','profile_rank','topic_profile_count')}
        for name,removed in ablations.items():
            path=models_dir/f'{name}.json'
            reports[name]=train_lambdamart(training,validation,path,
                {**metadata,'use_cross_encoder':name!='without_cross'},seed=config['seed'],removed=removed,
                settings=[reports['full']['parameters']],feature_names=EVIDENCE_FEATURES)
            models[name]=json.loads(path.read_text())
        evaluation=evaluate_rankings(engine,validation,models)
        names=['reference','without_cross','without_author_features','without_graph','full']
        selected=max(names,key=lambda n:(evaluation['metrics'][n]['ndcg_at_10'],evaluation['metrics'][n]['mrr']))
        model={**models[selected],'selection_name':selected}
        write_json(models_dir/'selected.json',model)
        if package_digest()!=code:raise RuntimeError('Code changed during model experiment; rerun from compatible caches before freezing')
        write_json(out,{'scope':'Train/validation selection only; reserved test not opened.','command':sys.argv,
            'config':{k:v for k,v in config.items() if not k.startswith('_')},'selected_settings':settings,
            'cohort_report_sha256':digest_file(config['cohort_report']) if 'cohort_report' in config else None,
            'query_adapter_file':adapter_file,'config_sha256':digest_file(args.config),'package_source_sha256_start':code,'package_source_sha256_end':package_digest(),
            'training':reports,'training_windows':windows,'validation':evaluation,
            'diagnostics':discovery_diagnostics(validation,set(engine.authors),model,engine.author_papers),
            'name_counterfactual':name_counterfactual(engine,model,queries[:20]),
            'selected':selected,'selected_model':str(models_dir/'selected.json'),'selected_model_sha256':digest_file(models_dir/'selected.json'),
            'runner_sha256':digest_file(__file__),'adapter_runner_sha256':digest_file(Path(__file__).with_name('train_query_adapters.py')),
            'environment':{'python':platform.python_version(),'compute':'local CPU','lightgbm':__import__('lightgbm').__version__},
            'ablation_scope':'All feature ablations share candidates, labels and LambdaRank negative rows. Graph/profile candidate channels remain. Classifier reference uses the same 48 hard +16 tail rows but its own objective/weights.',
            'limitations':['Automatic future authorship is incomplete relevance supervision.','Declared venue-portfolio benchmark, not random DBLP or human suitability judgments.','Different rolling snapshots at train/validation/inference are intentional and source-bound.'],
            'elapsed_seconds':round(monotonic()-started,3)})
        print(json.dumps({'selected':selected,'validation':evaluation['metrics'],'report':str(out)},indent=2))
    finally:engine.close();db.close()

if __name__=='__main__':main()
