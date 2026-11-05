#!/usr/bin/env python3
"""Fit residual query projections from allowed historical positive evidence only."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from threadpoolctl import threadpool_limits

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,package_digest,write_json
from hiresense.db import connect
from hiresense.evaluation.recovery import load_window
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex
from hiresense.retrieval.adaptation import QueryAdapter


def _train_adapters(config):
    work=Path(config['work']);report=work/'query-adapters.json'
    if report.exists():
        saved=json.loads(report.read_text())
        if saved['package_source_sha256']!=package_digest() or saved.get('runner_sha256')!=digest_file(__file__):raise ValueError('Query adapter code differs from its run')
        for window in saved['training_windows']:
            directory=Path(config['source_work'])/window['role']
            manifest=json.loads((directory/'manifest.json').read_text())
            index=json.loads((directory/'index/manifest.json').read_text())
            if digest_file(directory/'labels.jsonl')!=window['labels_sha256'] or manifest['labels_sha256']!=window['labels_sha256'] or index['content_sha256']!=window['graph_content_sha256']:
                raise ValueError('Query adapter training labels or graph changed')
        for item in saved['models']:
            if digest_file(item['path'])!=item['sha256']:raise ValueError('Query adapter artifact changed')
        return saved['models']
    work.mkdir(parents=True,exist_ok=True)
    encoder=LocalEncoder(config['encoder']);x=[];targets=[];windows=[];skipped=0
    for role in config['train_roles']:
        directory=Path(config['source_work'])/role;db=connect(directory/'graph.sqlite3');engine=None
        try:
            queries,sha=load_window(directory,db);engine=SearchIndex(db,directory/'index',encoder)
            vectors=encoder.encode([q.text for q in queries])
            for q,vector in zip(queries,vectors):
                evidence=[]
                for author in q.relevant_author_ids:
                    indices=engine.author_papers.get(author,[])
                    if indices:
                        values=np.asarray(engine.vectors[indices] @ vector)
                        position=int(np.argmax(values))
                        if values[position]>=.25:evidence.append((float(values[position]),indices[position]))
                if not evidence:
                    skipped+=1;continue
                evidence=sorted(evidence,key=lambda v:(-v[0],v[1]))[:3]
                weights=np.exp(np.asarray([v[0] for v in evidence])*5);weights/=weights.sum()
                target=(np.asarray(engine.vectors[[v[1] for v in evidence]])*weights[:,None]).sum(axis=0)
                target/=max(float(np.linalg.norm(target)),1e-9)
                x.append(vector);targets.append(target)
            windows.append({'role':role,'labels_sha256':sha,'graph_content_sha256':engine.manifest['content_sha256']})
        finally:
            if engine:engine.close()
            db.close()
    if len(x)<30:raise ValueError('Insufficient historical positive evidence for a query adapter')
    x=np.asarray(x,dtype=np.float32);delta=np.asarray(targets,dtype=np.float32)-x
    models=[]
    for alpha in (1.,10.,100.):
        with threadpool_limits(limits=2):
            fitted=Ridge(alpha=alpha,solver='cholesky').fit(x,delta)
        model={'version':'query-residual-ridge-v1','matrix':(fitted.coef_.T*.5).tolist(),
            'bias':(fitted.intercept_*.5).tolist(),'alpha':alpha,'residual_weight':.5,
            'training_queries':len(x),'queries_without_eligible_positive_evidence':skipped,
            'training_windows':windows,'label_policy':'Train-only future author labels select each known author\'s most similar allowed historical paper; top-three weak evidence targets, cosine>=.25. Non-author targets are never inferred. Not transformer fine-tuning.'}
        adapter=QueryAdapter(model,encoder.dimensions)
        expected=x[:10]+.5*fitted.predict(x[:10]);expected/=np.maximum(np.linalg.norm(expected,axis=1,keepdims=True),1e-9)
        if not np.allclose(np.asarray([adapter.transform(v) for v in x[:10]]),expected,atol=1e-6):
            raise ValueError('Portable query adapter differs from fitted Ridge')
        path=work/f'query-adapter-a{int(alpha)}.json';write_json(path,model)
        models.append({'name':f'adapter-a{int(alpha)}','path':str(path),'sha256':digest_file(path)})
    write_json(report,{'package_source_sha256':package_digest(),'models':models,'training_queries':len(x),
        'skipped_queries':skipped,'training_windows':windows,'runner_sha256':digest_file(__file__),'scope':'Training-only weak positive adaptation; validation will decide whether it helps. No validation/test labels fitted.'})
    print(f'Trained query adapters from {len(x)} historical evidence targets; {skipped} queries skipped.',flush=True)
    return models

def train_adapters(config):
    with threadpool_limits(limits=2):
        return _train_adapters(config)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    a=p.parse_args();print(json.dumps(train_adapters(json.loads(a.config.read_text())),indent=2))
