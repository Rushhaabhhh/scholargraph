#!/usr/bin/env python3
"""Fit contextual identity decisions on earlier observations; reserve a later check."""
import argparse
import hashlib
import heapq
import json
import math
import random
import resource
import sys
from pathlib import Path
from time import monotonic

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import PolynomialFeatures,StandardScaler
from threadpoolctl import threadpool_limits

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,package_digest,write_json
from hiresense.data.noise import corrupt_name,visible_name
from hiresense.db import connect
from hiresense.evaluation.split import dataset_digest
from hiresense.graph.resolution import AuthorMatcher
from hiresense.graph.identity_model import IDENTITY_FEATURES,identity_features,IdentityScorer

WORK=Path('data/processed/recovery-identity-v2')
OUT=Path('results/recovery-identity-model-v2.json')


def old_observed_papers(source):
    # Reconstruct the exact prior sample's random draws, without scoring again.
    rng=random.Random(314159);keys=set()
    for paper in source.execute('SELECT id,year,venue FROM papers WHERE year BETWEEN 2023 AND 2024 ORDER BY id'):
        authors=source.execute('SELECT author_id,observed_name FROM paper_authors WHERE paper_id=? ORDER BY author_position',(paper['id'],)).fetchall()
        for author in authors:
            if rng.random()>=.01:continue
            kind=rng.choice(('initials','name_order','typo','transliteration'))
            corrupt_name(author['observed_name'],kind,rng)
            for other in authors:
                if other['author_id']!=author['author_id']:rng.random()
            keys.add(paper['id'])
    return keys


def observations(source,start,end,count,role,excluded):
    heap=[]
    for paper in source.execute('SELECT id,year,venue FROM papers WHERE year BETWEEN ? AND ? ORDER BY id',(start,end)):
        if paper['id'] in excluded:continue
        authors=source.execute('SELECT author_id,observed_name,author_position FROM paper_authors WHERE paper_id=? ORDER BY author_position',(paper['id'],)).fetchall()
        for author in authors:
            key=f"{paper['id']}:{author['author_position']}"
            priority=int.from_bytes(hashlib.sha256(f'271828:{role}:{key}'.encode()).digest(),'big')
            if len(heap)==count and priority>=-heap[0][0]:continue
            item=(-priority,key,dict(paper),[dict(a) for a in authors],dict(author))
            if len(heap)<count:heapq.heappush(heap,item)
            else:heapq.heapreplace(heap,item)
    result=[]
    for _,key,paper,authors,author in sorted(heap,key=lambda v:(-v[0],v[1])):
        rng=random.Random(hashlib.sha256(f'noise:{role}:{key}'.encode()).hexdigest())
        kind=rng.choice(('initials','name_order','typo','transliteration'))
        record={'noisy_name':corrupt_name(author['observed_name'],kind,rng),
                'observed_years':[paper['year']],'observed_venues':[paper['venue']] if paper['venue'] else [],
                'observed_coauthors':[visible_name(a['observed_name']) for a in authors if a['author_id']!=author['author_id'] and rng.random()>=.15]}
        result.append((key,record,author['author_id'],kind))
    if len(result)!=count:raise ValueError('Insufficient observations')
    return result


def prepare(matcher,records):
    output=[]
    for key,record,truth,kind in records:
        ids,_,_=matcher.candidates(record);x,supported=identity_features(matcher,record,ids)
        baseline=matcher.match(record)[0]
        output.append({'key':key,'ids':ids,'x':x,'supported':supported,'truth':truth,
                       'known':truth in matcher.profiles,'kind':kind,'baseline':baseline})
    return output


def summarize(rows,decisions):
    n=len(rows);known=sum(r['known'] for r in rows);assigned=sum(v is not None for v in decisions)
    correct=sum(r['known'] and v==r['truth'] for r,v in zip(rows,decisions))
    wrong=sum(v is not None and v!=r['truth'] for r,v in zip(rows,decisions))
    return {'observations':n,'known':known,'assigned':assigned,'correct':correct,'incorrect_merges':wrong,
        'precision':correct/assigned if assigned else None,'known_recall':correct/known if known else None,
        'candidate_recall_known':sum(r['known'] and r['truth'] in r['ids'] for r in rows)/max(1,known),
        'unknown_incorrect_merges':sum(not r['known'] and v is not None for r,v in zip(rows,decisions))}


def main():
    global WORK, OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--precision-target',type=float,default=.995)
    parser.add_argument('--margin-max',type=int,default=3)
    parser.add_argument('--exclude-previous-test',action='store_true')
    parser.add_argument('--work',type=Path,default=WORK)
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args();WORK=args.work;OUT=args.out
    if not .99<=args.precision_target<=1 or args.margin_max<3:raise ValueError('Require a high-precision calibration target and positive margin grid')
    if OUT.exists():raise ValueError('Use a new experiment path')
    WORK.mkdir(parents=True,exist_ok=True);began=monotonic();code=package_digest()
    source=connect('data/processed/recovery-v2/source.sqlite3');graph=connect('data/processed/recovery-v2/train-early/graph.sqlite3')
    try:
        if dataset_digest(source)!=graph.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()[0]:raise ValueError('Identity source provenance differs')
        excluded=old_observed_papers(source)
        prior=connect('data/processed/history-enriched/source.sqlite3')
        try:
            excluded.update(row[0] for row in prior.execute('SELECT id FROM papers WHERE year BETWEEN 2023 AND 2024'))
        finally:prior.close()
        extra_excluded=0
        if args.exclude_previous_test:
            prior_test=observations(source,2024,2024,4000,'reserved-test',excluded)
            previous_papers={row[0].rsplit(':',1)[0] for row in prior_test}
            extra_excluded=len(previous_papers-excluded);excluded.update(previous_papers)
        matcher=AuthorMatcher(graph,year_mode='distance',policy='conservative')
        train=prepare(matcher,observations(source,2021,2022,4000,'train',set()))
        valid=prepare(matcher,observations(source,2023,2023,2000,'validation',excluded))
        x=[];y=[]
        for r in train:
            for i,a in enumerate(r['ids']):
                if r['supported'][i]:x.append(r['x'][i]);y.append(a==r['truth'])
        x=np.asarray(x);y=np.asarray(y,dtype=np.int32)
        if len(set(y.tolist()))!=2:raise ValueError('Insufficient contextual positive/contrast examples')
        polynomial=PolynomialFeatures(degree=2,include_bias=False);expanded=polynomial.fit_transform(x)
        scaler=StandardScaler().fit(expanded);z=scaler.transform(expanded)
        trials=[]
        for c in (.1,1.,10.):
            with threadpool_limits(limits=2):
                fitted=LogisticRegression(C=c,class_weight='balanced',max_iter=1000,random_state=271828).fit(z,y)
            model={'version':'contextual-identity-logistic-v1','features':list(IDENTITY_FEATURES),
                'powers':polynomial.powers_.tolist(),'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),
                'weights':fitted.coef_[0].tolist(),'intercept':float(fitted.intercept_[0]),'C':c,
                'logit_threshold':0.,'margin_threshold':.5,'training_graph_cutoff':2020,
                'scope':'Earlier noisy observation pairs with independent shared-coauthor gate; class-balanced scores are not calibrated probabilities.'}
            scorer=IdentityScorer(model)
            if not np.allclose(scorer.logits(x),fitted.decision_function(z),atol=1e-8):raise ValueError('Portable identity predictions differ')
            summaries=[]
            for r in valid:
                v=scorer.logits(r['x'])
                if not len(v):summaries.append((None,-math.inf,0,False));continue
                order=np.lexsort((np.asarray(r['ids']),-v));i=order[0]
                summaries.append((r['ids'][i],float(v[i]),float(v[i]-v[order[1]]) if len(order)>1 else 100.,bool(r['supported'][i])))
            for threshold in (0.,1.,2.,3.,4.,5.,6.,7.,8.,9.,10.):
                for margin in [.5]+[float(i) for i in range(1,args.margin_max+1)]:
                    decisions=[a if ok and score>=threshold and gap>=margin else None for a,score,gap,ok in summaries]
                    stats=summarize(valid,decisions)
                    if stats['assigned']>=50 and stats['precision']>=args.precision_target:
                        trials.append((stats['known_recall'],stats['precision'],-c,{**model,'logit_threshold':threshold,'margin_threshold':margin},stats))
        if not trials:raise ValueError('No identity setting meets validation precision/support gate')
        _,_,_,chosen,validation=max(trials,key=lambda r:(r[0],r[1],r[2]))
        selected=WORK/'selected.json';write_json(selected,chosen)
        # Only now open the reserved later observations and report without retuning.
        test=prepare(matcher,observations(source,2024,2024,4000,'reserved-test-strict' if args.exclude_previous_test else 'reserved-test',excluded))
        scorer=IdentityScorer(chosen)
        decisions=[scorer.choose(r['ids'],r['x'],r['supported'])[0] for r in test]
        measured=summarize(test,decisions);baseline=summarize(test,[r['baseline'] for r in test])
        adoption=measured['assigned']>=50 and measured['precision']>=.99 and measured['known_recall']>=.8*baseline['known_recall']
        if package_digest()!=code:raise ValueError('Code changed during identity model experiment')
        write_json(OUT,{'scope':'Contextual identity model; validation-only selection, fresh 2024 test observations excluding entire previously sampled papers.',
            'package_source_sha256':code,'runner_sha256':digest_file(__file__),'selected_model':str(selected),'selected_model_sha256':digest_file(selected),
            'train_observations':len(train),'train_pairs':len(x),'positive_pairs':int(y.sum()),'validation':validation,
            'test':measured,'conservative_same_test':baseline,'adoption_gate_met':adoption,'adoption_rule':'At least 50 test assignments, >=99% point precision and >=80% of conservative recall; at most 20% relative recall loss is allowed because incorrect merges cost more. No threshold retuning on test.',
            'excluded_old_sample_papers':len(excluded),
            'selection':f'Maximize known recall at >={args.precision_target:.3%} validation assignment precision with >=50 assignments; evaluate once on fresh reserved 2024 observations.',
            'config':{'precision_target':args.precision_target,'margin_max':args.margin_max,'exclude_previous_test':args.exclude_previous_test,'additional_excluded_previous_test_papers':extra_excluded},
            'selected_parameters':{k:chosen[k] for k in ('C','logit_threshold','margin_threshold')},
            'elapsed_seconds':monotonic()-began,'process_peak_rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'limitations':['Synthetic noise; coauthor names are suffix-stripped and partially dropped, not fully corrupted.','Known-reference linkage, not open-world clustering.','Finite sample precision is not a guarantee.','Canonical DBLP graph is never relabeled by these proposals.']})
        print(json.dumps({'validation':validation,'test':measured,'baseline':baseline,'adoption':adoption},indent=2))
    finally:source.close();graph.close()

if __name__=='__main__':main()
