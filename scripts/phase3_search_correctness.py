#!/usr/bin/env python3
"""Compare lexical-only abstention with an exploratory cosine gate; no promotion."""
import json,sys,tempfile,time
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.api.runtime import Backend
from hiresense.data.artifacts import write_json,digest_file
from hiresense.retrieval.index import tokens

out=Path('resources/results/phase3-search-correctness.json')
if out.exists():raise ValueError('Use new output')
# Manually authored, synthetic single-paper topic pairs; these are engineering
# examples, not independent expert relevance judgements.
pairs=[('information retrieval','search engine'),('earth observation imagery','satellite pictures'),('neural network compression','deep learning model pruning'),('computer vision','visual object recognition'),('network security','cyber attack detection'),('natural language processing','computational linguistics'),('reinforcement learning','learning by reward'),('distributed database','decentralized data storage')]
negative=['zxqvplm wkrjty nonsensephrase','qzxvplm qoweyu blarnyx','asdfghjkl zxcvbnm qwertyu','flarbington wozzy flumples','qwertyuiopasdf zzzxyyzz','zzqvvbb rrtyyuu wwaaqq','nmmzqx vbbnkl frpppp','xyzzzz vvvqqa qwdzzz']
with tempfile.TemporaryDirectory(prefix='phase3-search-') as tmp:
 b=Backend.load('resources/experiments/backend.json',session_db_override=Path(tmp)/'sessions.sqlite')
 try:
  e=b.engine.encoder;a=e.encode([q for q,t in pairs]);v=e.encode([t for q,t in pairs]);positive=np.sum(a*v,axis=1);n=e.encode(negative)
  with threadpool_limits(limits=2,user_api='blas'):neg=np.max(b.engine.vectors@n.T,axis=0)
  # First four positives / negatives calibrate a simple threshold. Remaining
  # examples are held back to illustrate trade-offs; no claims of calibration.
  cut=(float(max(neg[:4]))+float(min(x for x in positive[:4] if x>max(neg[:4]))))/2
  positive_details=[{'query':q,'title':t,'shared_tokens':sorted(tokens(q)&tokens(t)),'cosine':float(s),'cohort':'calibration' if i<4 else 'holdout','existing_would_abstain':not bool(tokens(q)&tokens(t)),'alternative_accepts':bool(s>=cut)} for i,((q,t),s) in enumerate(zip(pairs,positive))]
  negative_details=[{'query':q,'best_corpus_cosine':float(s),'cohort':'calibration' if i<4 else 'holdout','alternative_accepts':bool(s>=cut)} for i,(q,s) in enumerate(zip(negative,neg))]
  checks=[]
  for q,params in [('graph neural networks since 2022',{}),('graph neural networks since 2022',{'recency_preference':'any'}),('zxqvplm wkrjty nonsensephrase',{})]:
   result=b.search({'query':q,**params});checks.append({'query':q,'overrides':params,'effective_filters':result['effective_filters'],'result_count':len(result['results']),'oldest_evidence_year':min((p['year'] for a in result['results'] for p in a['evidence'] if p['year'] is not None),default=None)})
  report={'scope':'Tiny manually authored single-paper paraphrase examples and synthetic gibberish; cosine threshold is exploratory only and NOT deployed or calibrated for production.','command':sys.argv,'model_sha256':digest_file('models/hybrid_ranker.json'),'threshold':cut,'threshold_selection':'Midpoint between largest calibration negative best-corpus cosine and smallest larger calibration positive pair cosine.', 'positives':positive_details,'negatives':negative_details,'holdout_positive_accepted':sum(x['alternative_accepts'] for x in positive_details[4:]),'holdout_negative_accepted':sum(x['alternative_accepts'] for x in negative_details[4:]),'live_checks':checks,'production_behavior':'Unchanged lexical-overlap abstention; known zero-overlap false abstention remains.', 'limitations':['Positive synthetic pairs are not drawn from a randomly sampled realistic query distribution or independently judged.','Positive pair and negative full-corpus maxima are different search settings.','Too small to establish accuracy or safe OOD/false-acceptance rates.','A shared lexical term does not establish topical relevance.']}
  write_json(out,report);print(json.dumps(report,indent=2))
 finally:b.close()
