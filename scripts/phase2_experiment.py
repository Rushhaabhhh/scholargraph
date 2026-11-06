#!/usr/bin/env python3
"""CPU-only fixed-candidate evidence/graph ranker experiment; separate stages."""
import argparse, hashlib, json, os, resource, sqlite3, sys, tempfile, time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file, write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.models import GroundTruthQuery
from hiresense.ranking.evidence import EVIDENCE_FEATURES, GRAPH_FEATURES, evidence_features, eligible_lexical_max, graph_features
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex

ROOT=Path('data/processed/phase2-v1');COHORT=Path('resources/experiments/phase2-cohorts-v1.json');MODEL=Path('models/hybrid_ranker.json');FREEZE=ROOT/'freeze.json'
NAMES=FEATURE_NAMES+EVIDENCE_FEATURES+GRAPH_FEATURES

def get_queries(role,cohort):
 if role=='train':return load_queries('data/processed/lean-v1/train/labels.jsonl')
 source=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
 try:
  if digest_file('data/processed/lean-v1/source.sqlite3')!=cohort['source_db_sha256']:raise ValueError('Source DB changed')
  output=[]
  for key in cohort['reserved_source_paper_ids'][role]:
   row=source.execute('select id,title,year from papers where id=?',(key,)).fetchone();authors=tuple(x[0] for x in source.execute('select author_id from paper_authors where paper_id=? order by author_position',(key,)))
   if not row or not authors:raise ValueError('Reserved query lacks source or authors')
   output.append(GroundTruthQuery(row[0],row[1],row[0],row[2],authors))
  return output
 finally:source.close()

def materialize(role):
 if role=='final' and not FREEZE.exists():raise ValueError('Freeze model and protocol before opening final labels')
 if role=='final':
  frozen=json.loads(FREEZE.read_text())
  if (digest_file(COHORT)!=frozen['cohort_sha256'] or digest_file(MODEL)!=frozen['production_model_sha256']
      or digest_file(ROOT/'B2.txt')!=frozen['spec']['model_sha256']
      or digest_file('src/hiresense/ranking/evidence.py')!=frozen['evidence_code_sha256']
      or digest_file('data/indexes/recent-history/manifest.json')!=frozen['final_graph_index_manifest_sha256']
      or digest_file('resources/results/phase2-model-comparison.json')!=frozen['validation_report_sha256']):
   raise ValueError('Frozen artifact changed before final labels opened')
 ROOT.mkdir(parents=True,exist_ok=True);path=ROOT/f'{role}.npz';meta_path=ROOT/f'{role}.json'
 if path.exists() or meta_path.exists():raise ValueError('Cache exists; use or inspect existing experiment')
 cohort=json.loads(COHORT.read_text());queries=get_queries(role,cohort);graph=Path('data/processed/recent-history') if role=='final' else Path('data/processed/lean-v1')/('train' if role=='train' else 'validation')
 idx=Path('data/indexes/recent-history') if role=='final' else graph/'index';db=connect(graph/'graph.sqlite3');engine=None;start=time.monotonic()
 try:
  cutoff=2024 if role=='final' else 2020 if role=='train' else 2023
  assert_no_leakage(db,queries,[],cutoff)
  engine=SearchIndex(db,idx,LocalEncoder(),paper_limit=1024,candidate_limit=800);ids=[];features=[];offsets=[0];labels=[];rawlabels=[]; knownlabels=[];lexical=[]; dense=[];times=[]
  source=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
  for author in {a for q in queries for a in q.relevant_author_ids if a in engine.authors}:
   left=source.execute('select source_key from authors where id=?',(author,)).fetchone();right=db.execute('select source_key from authors where id=?',(author,)).fetchone()
   if not left or not right or left[0]!=right[0]:raise ValueError('Target author source identity mismatch')
  source.close()
  for i,q in enumerate(queries):
   t=time.monotonic();ctx=engine.candidate_context(q.text);authors=sorted(ctx['fused'],key=lambda x:(-ctx['fused'][x],x))[:800];base=engine.assemble(q.text,authors,ctx);lm=eligible_lexical_max(engine,ctx)
   extras=[evidence_features(engine,ctx,a,q.text,lexical_max=lm)+graph_features(engine,ctx,a,q.text) for a in authors]
   features.append(np.column_stack((base['features'],np.asarray(extras,dtype=np.float32))) if authors else np.empty((0,len(NAMES)),dtype=np.float32));ids.extend(authors);offsets.append(len(ids));targets=set(q.relevant_author_ids);labels.extend(int(x in targets) for x in authors);rawlabels.append(sorted(targets));knownlabels.append(sorted(targets.intersection(engine.authors)));lexical.append(ctx['lexical'][:800]);dense.append(ctx['dense'][:800]);times.append((time.monotonic()-t)*1000)
   if (i+1)%50==0:print(role,i+1,'/',len(queries),flush=True)
  np.savez_compressed(path,features=np.concatenate(features),ids=np.asarray(ids,dtype=np.int64),offsets=np.asarray(offsets,dtype=np.int64),labels=np.asarray(labels,dtype=np.uint8))
  meta={'role':role,'query_ids':[q.query_id for q in queries],'target_ids':rawlabels,'known_target_ids':knownlabels,'lexical':lexical,'dense':dense,'query_venue_groups':[q.source_paper_id.split('/')[1] if '/' in q.source_paper_id else 'other' for q in queries], 'feature_names':NAMES,'cutoff':cutoff,'graph_content_sha256':engine.manifest['content_sha256'],'encoder_sha256':engine.encoder.signature,'candidate_settings':{'paper_limit':1024,'candidate_limit':800},'cohort_sha256':digest_file(COHORT),'evidence_code_sha256':digest_file('src/hiresense/ranking/evidence.py'),'cache_sha256':digest_file(path),'queries':len(queries),'p95_feature_generation_ms':float(np.percentile(times,95)),'p50_feature_generation_ms':float(np.percentile(times,50)),'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'elapsed_seconds':round(time.monotonic()-start,2)}
  write_json(meta_path,meta);print(json.dumps({k:meta[k] for k in ('role','queries','elapsed_seconds','p95_feature_generation_ms','peak_rss_mib')}),flush=True)
 finally:
  if engine:engine.close()
  db.close()

def load(role):
 path=ROOT/f'{role}.npz';meta=json.loads((ROOT/f'{role}.json').read_text())
 if digest_file(path)!=meta['cache_sha256'] or digest_file(COHORT)!=meta['cohort_sha256'] or digest_file('src/hiresense/ranking/evidence.py')!=meta['evidence_code_sha256']:raise ValueError('Cache provenance changed')
 with np.load(path,allow_pickle=False) as f:data={k:f[k] for k in f.files}
 return data,meta

def rankmetrics(data,meta,score=None):
 rows=[]
 for i,targets in enumerate(meta['target_ids']):
  st,en=data['offsets'][i:i+2];ids=data['ids'][st:en];order=ids if score is None else ids[np.lexsort((ids,-score[st:en]))];rows.append(ranking_metrics(order[:10].tolist(),set(targets)))
 return rows

def average(rows):return {key:float(np.mean([r[key] for r in rows])) for key in ('ndcg_at_10','mrr_at_10','hit_at_10')}

def train():
 from lightgbm import LGBMRanker
 if FREEZE.exists():raise ValueError('Experiment already frozen')
 train,tm=load('train');val,vm=load('validation');rng=np.random.default_rng(42);rows=[];groups=[]
 for i in range(len(tm['query_ids'])):
  s,e=train['offsets'][i:i+2];pos=np.flatnonzero(train['labels'][s:e])+s;neg=np.flatnonzero(1-train['labels'][s:e])+s
  if not len(pos) or not len(neg):continue
  hard=neg[:48];tail=rng.choice(neg[48:],min(16,len(neg)-48),replace=False) if len(neg)>48 else []
  group=np.concatenate((pos,hard,tail)).astype(int);rows.extend(group);groups.append(len(group))
 rows=np.asarray(rows);base=json.loads(MODEL.read_text());base_score=score_model(val['features'][:,:len(FEATURE_NAMES)],base);baseline=rankmetrics(val,vm,base_score);hybrid=rankmetrics(val,vm)
 topical={'strong_papers_log','strong_concentration_smoothed','combined_top3_weighted'}
 recency={'matched_recency','author_recency','recent_strong_log','strong_most_recent_decay','topical_recency_weighted'}
 graph=set(GRAPH_FEATURES);degree={'log_collaborators'}
 specs={'B2':graph,'B3':graph|topical,'B4':graph|recency,'G0':graph|degree,'G1':graph,'G2':degree}
 results={'B0':average(hybrid),'B1':average(baseline)};scores={};training={}
 for name,drop in specs.items():
  keep=[i for i,x in enumerate(NAMES) if x not in drop];model=LGBMRanker(objective='lambdarank',n_estimators=80,num_leaves=7,learning_rate=.04,min_child_samples=30,reg_lambda=2,n_jobs=2,random_state=42,deterministic=True,force_col_wise=True,verbosity=-1);t=time.monotonic();model.fit(train['features'][rows][:,keep],train['labels'][rows],group=groups)
  path=ROOT/f'{name}.txt';model.booster_.save_model(str(path));raw=model.predict(val['features'][:,keep]);prior=val['features'][:,FEATURE_NAMES.index('hybrid_rrf')];trials=[]
  for alpha in (0.,.25,.5,.75,1.):
   values=alpha/(1+np.exp(-np.clip(raw,-40,40)))+(1-alpha)*prior;metrics=average(rankmetrics(val,vm,values));trials.append((metrics['ndcg_at_10'],metrics['mrr_at_10'],alpha,metrics))
  best=max(trials);scores[name]=best[2]/(1+np.exp(-np.clip(raw,-40,40)))+(1-best[2])*prior;results[name]=best[3];training[name]={'features':[NAMES[i] for i in keep],'blend_alpha':best[2],'model_sha256':digest_file(path),'elapsed_seconds':round(time.monotonic()-t,2),'trials':[{'blend':t[2],'metrics':t[3]} for t in trials]};print(name,results[name],flush=True)
 selected='B2';report={'scope':'Previously reserved 2024 validation, automatic future-authorship labels; selection and ablations share fixed candidates. Not final test.','metrics':results,'training':training,'seed':42,'examples':len(rows),'groups':len(groups),'train_cache_sha256':tm['cache_sha256'],'validation_cache_sha256':vm['cache_sha256']}
 paired={};rng=np.random.default_rng(42);sample=rng.integers(0,len(baseline),(5000,len(baseline)))
 for name,values in scores.items():
  rs=rankmetrics(val,vm,values);paired[name]={}
  for key in ('ndcg_at_10','mrr_at_10','hit_at_10'):
   delta=np.array([a[key]-b[key] for a,b in zip(rs,baseline)]);paired[name][key]={'delta':float(delta.mean()),'paired_95pct':np.quantile(delta[sample].mean(axis=1),[.025,.975]).tolist()}
 report['paired_vs_B1']=paired;write_json(Path('resources/results/phase2-model-comparison.json'),report)
 graphreport={'scope':'Matched candidates, retrained models; G0 excludes collaborator count and query-specific graph features; G1 adds count; G2 adds query-specific features without count. Blend individually selected on validation.','metrics':{k:results[k] for k in ('G0','G1','G2')},'training':{k:training[k] for k in ('G0','G1','G2')},'paired':{}}
 for name in ('G1','G2'):
  graphreport['paired'][name]={};left=rankmetrics(val,vm,scores[name]);right=rankmetrics(val,vm,scores['G0'])
  for key in ('ndcg_at_10','mrr_at_10','hit_at_10'):
   d=np.array([a[key]-b[key] for a,b in zip(left,right)]);graphreport['paired'][name][key]={'delta':float(d.mean()),'paired_95pct':np.quantile(d[sample].mean(axis=1),[.025,.975]).tolist()}
 write_json(Path('resources/results/phase2-graph-ablation.json'),graphreport)
 freeze={'scope':'Frozen before final labels are opened; experimental B2 only, production unchanged.','selected':selected,'spec':training[selected],'retrieval':{'paper_limit':1024,'candidate_limit':800},'cohort_sha256':digest_file(COHORT),'evidence_code_sha256':digest_file('src/hiresense/ranking/evidence.py'),'production_model_sha256':digest_file(MODEL),'validation_report_sha256':digest_file('resources/results/phase2-model-comparison.json'),'validation_graph_content_sha256':vm['graph_content_sha256'],'final_graph_index_manifest_sha256':digest_file('data/indexes/recent-history/manifest.json'),'final_graph_cutoff':2024,'protocol':'Identical candidate pool, B0/B1/B2, lexical and dense, nDCG@10 MRR@10 Hit@10 and paired bootstrap. No model tuning on final.'}
 write_json(FREEZE,freeze)

def final():
 import lightgbm as lgb
 if Path('resources/results/phase2-final-evaluation.json').exists():raise ValueError('Final evaluation already exists; do not overwrite an inspected test')
 f=json.loads(FREEZE.read_text());data,meta=load('final')
 if digest_file(MODEL)!=f['production_model_sha256'] or digest_file(ROOT/'B2.txt')!=f['spec']['model_sha256'] or digest_file('data/indexes/recent-history/manifest.json')!=f['final_graph_index_manifest_sha256'] or digest_file('resources/results/phase2-model-comparison.json')!=f['validation_report_sha256']:raise ValueError('Frozen artifact changed')
 model=lgb.Booster(model_file=str(ROOT/'B2.txt'));keep=[NAMES.index(x) for x in f['spec']['features']];raw=model.predict(data['features'][:,keep],num_threads=2);alpha=f['spec']['blend_alpha'];prior=data['features'][:,FEATURE_NAMES.index('hybrid_rrf')];s=alpha/(1+np.exp(-np.clip(raw,-40,40)))+(1-alpha)*prior
 b1=rankmetrics(data,meta,score_model(data['features'][:,:len(FEATURE_NAMES)],json.loads(MODEL.read_text())));b2=rankmetrics(data,meta,s);b0=rankmetrics(data,meta)
 rng=np.random.default_rng(42);sample=rng.integers(0,len(b1),(5000,len(b1)));paired={}
 for k in ('ndcg_at_10','mrr_at_10','hit_at_10'):
  delta=np.array([a[k]-b[k] for a,b in zip(b2,b1)]);paired[k]={'delta':float(delta.mean()),'paired_95pct':np.quantile(delta[sample].mean(axis=1),[.025,.975]).tolist()}
 baselines={}
 for name in ('lexical','dense'):
  baselines[name]=average([ranking_metrics(order[:10],set(target)) for order,target in zip(meta[name],meta['target_ids'])])
 groups={}
 for group in sorted(set(meta['query_venue_groups'])):
  idx=[i for i,x in enumerate(meta['query_venue_groups']) if x==group]
  if len(idx)>=10:groups[group]={'queries':len(idx),'B1':average([b1[i] for i in idx]),'B2':average([b2[i] for i in idx])}
 known_idx=[i for i,targets in enumerate(meta['known_target_ids']) if targets];known_meta={**meta,'target_ids':meta['known_target_ids']};b1known=rankmetrics(data,known_meta,score_model(data['features'][:,:len(FEATURE_NAMES)],json.loads(MODEL.read_text())));b2known=rankmetrics(data,known_meta,s)
 known_hits=sum(sum(a in set(meta['known_target_ids'][i]) for a in data['ids'][data['offsets'][i]:data['offsets'][i+1]]) for i in range(len(b1)))
 output={'scope':'One evaluation on reserved 2025 future-authorship proxy queries; historic exposure not completely audited; not human accuracy. Now inspected.', 'freeze_sha256':digest_file(FREEZE),'final_cache_sha256':meta['cache_sha256'],'query_count':len(b1),'metrics':{'lexical':baselines['lexical'],'dense':baselines['dense'],'B0':average(b0),'B1':average(b1),'B2':average(b2)},'paired_B2_minus_B1':paired,'known_author_diagnostic':{'queries_with_known':len(known_idx),'known_author_instances':sum(map(len,meta['known_target_ids'])),'candidate_recall':known_hits/max(1,sum(map(len,meta['known_target_ids']))),'B1':average([b1known[i] for i in known_idx]),'B2':average([b2known[i] for i in known_idx]),'scope':'Only queries with known target authors; nDCG ideal excludes unknown targets, not comparable to overall.'},'venue_groups_min10':groups,'feature_generation_latency_ms':{'p50':meta['p50_feature_generation_ms'],'p95':meta['p95_feature_generation_ms']},'peak_rss_mib':meta['peak_rss_mib'],'recommendation':'retain production pending performance, serving and independent validation gates'}
 write_json(Path('resources/results/phase2-final-evaluation.json'),output);print(json.dumps(output,indent=2))

p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['train-features','validation-features','fit','final-features','final-evaluate']);args=p.parse_args()
if args.action.endswith('-features'):materialize(args.action.split('-')[0])
elif args.action=='fit':train()
else:final()
