#!/usr/bin/env python3
"""Audit configured production and generate a blinded, unlabelled review pool."""
import csv,hashlib,json,random,sqlite3,subprocess,sys,tempfile,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.api.runtime import Backend
from hiresense.data.artifacts import digest_file,package_digest,write_json
from hiresense.ranking.scoring import score_model

paths=[Path('resources/results/phase3-production-audit.json'),Path('resources/experiments/phase3-judgment-pool.jsonl'),Path('resources/experiments/phase3-review-template.csv'),Path('resources/results/phase3-pool-methods-private.json')]
if any(p.exists() for p in paths):raise SystemExit('Use new output paths')
queries=[json.loads(line) for line in Path('resources/experiments/phase3-human-queries.jsonl').read_text().splitlines()];start=time.monotonic();pool=[];method_map=[];latencies=[];claims=0;errors=[]
with tempfile.TemporaryDirectory(prefix='phase3-audit-') as tmp:
 b=Backend.load('resources/experiments/backend.json',session_db_override=Path(tmp)/'sessions.sqlite')
 try:
  assert b.model['version']=='paper-lambdamart-v1' and b.model['retrieval_kind']=='paper'
  assert b.engine.paper_limit==1024 and b.engine.candidate_limit==800
  for no,item in enumerate(queries,1):
   q=item['query'];t=time.monotonic();answer=b.search({'query':q});again=b.search({'query':q})
   deterministic=answer['results']==again['results'];latencies.append((time.monotonic()-t)*500)
   cutoff=answer['effective_filters']['since_year'];text=answer['retrieval_query'];ctx=b.engine.candidate_context(text,since_year=cutoff);order=sorted(ctx['fused'],key=lambda a:(-ctx['fused'][a],a))[:800]
   retrieve=b.engine.assemble(text,order,ctx);scores=score_model(retrieve['features'],b.model);trained=sorted(order,key=lambda a:(-float(scores[order.index(a)]),a))
   methods={'lexical':ctx['lexical'][:10],'dense':ctx['dense'][:10],'hybrid':order[:10],'trained':trained[:10]}
   authors=list(set(a for ids in methods.values() for a in ids));random.Random(314159+no).shuffle(authors)
   # Each pooled person receives their own source-backed publication evidence.
   pooled=b.engine.assemble(text,authors,ctx);papers=b.verifier.explain(b.engine.results(text,pooled,np.arange(len(authors),dtype=float)*0,len(authors)),cutoff)
   by_id={p['person_id']:p for p in papers}
   for a in authors:
    person=by_id.get(a)
    if not person:continue
    evidence=[]
    for p in person['evidence']:
     venue=b.database.execute('select venue from papers where id=?',(p['paper_id'],)).fetchone()[0]
     evidence.append({'paper_id':p['paper_id'],'title':p['title'],'year':p['year'],'venue':venue,'source':p['source']})
     claims+=1
    pool.append({'query_id':item['query_id'],'query':q,'topic':item['topic'],'query_type':item['query_type'],'person_id':a,'author_name':person['name'],'evidence':evidence,'grade':None,'reviewer':None})
   method_map.append({'query_id':item['query_id'],'methods':methods})
   if not deterministic:errors.append({'query_id':item['query_id'],'issue':'nondeterministic'})
   if cutoff and any(p['year'] is None or p['year']<cutoff for x in answer['results'] for p in x['evidence']):errors.append({'query_id':item['query_id'],'issue':'date_violation'})
   if no%10==0:print('Audited',no,'/',len(queries),flush=True)
  cfg=json.loads(Path('resources/experiments/backend.json').read_text());reports={'scope':'Production runtime, 40 predetermined convenience topics. Timing averages two sequential searches and includes result verification, excludes HTTP and startup. Not relevance accuracy.','command':sys.argv,'source_sha256':package_digest(),'git_revision':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip(),'model_sha256':digest_file('models/hybrid_ranker.json'),'graph_content_sha256':b.engine.manifest['content_sha256'],'graph_file_sha256':digest_file('data/processed/recent-history/graph.sqlite3'),'index_manifest_sha256':digest_file('data/indexes/recent-history/manifest.json'),'model_version':b.model['version'],'retrieval_kind':b.model['retrieval_kind'],'paper_limit':b.engine.paper_limit,'candidate_limit':b.engine.candidate_limit,'graph_cutoff':b.engine.anchor_year,'papers':len(b.engine.papers),'authors':len(b.engine.authors),'query_provider':cfg['query_provider'],'experimental_routes_active':False,'queries':len(queries),'pooled_rows':len(pool),'evidence_entries':claims,'errors':errors,'sequential_search_latency_ms':{'p50':float(np.percentile(latencies,50)),'p95':float(np.percentile(latencies,95))},'human_judgments':'pending','baseline_scope':'Review pool is not labelled. Methods measured on identical graph but lexical/dense candidates can differ.'}
  with paths[1].open('w') as f:
   for row in pool:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  with paths[2].open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['query_id','query','person_id','author_name','evidence','grade_0_to_3','reviewer','notes']);w.writeheader()
   for r in pool:w.writerow({'query_id':r['query_id'],'query':r['query'],'person_id':r['person_id'],'author_name':r['author_name'],'evidence':json.dumps(r['evidence'],ensure_ascii=False),'grade_0_to_3':'','reviewer':'','notes':''})
  write_json(paths[3],{'scope':'Keep separate while judging; algorithm identity unblinded only after independent reviews.','methods':method_map})
  reports['review_pool_sha256']=digest_file(paths[1]);reports['review_template_sha256']=digest_file(paths[2]);reports['elapsed_seconds']=round(time.monotonic()-start,2);write_json(paths[0],reports);print(json.dumps(reports,indent=2))
 finally:b.close()
