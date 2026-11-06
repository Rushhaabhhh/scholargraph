#!/usr/bin/env python3
"""Small-sample sequential component timings; local CPU and no API keys."""
import json,resource,sys,tempfile,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import write_json,digest_file
from hiresense.data.ingest import ingest
from hiresense.db import connect,initialize
from hiresense.graph.build import build_context_graph
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.factory import search_index
from hiresense.retrieval.index import build_index
from hiresense.ranking.scoring import score_model
from hiresense.assistant.grounding import GroundingVerifier
from hiresense.batch import run_batch

out=Path('resources/results/phase3-component-benchmark.json')
if out.exists():raise ValueError('Use fresh output')
source=Path('resources/examples/sample.xml');queries=Path('resources/examples/queries.txt');model=json.loads(Path('models/hybrid_ranker.json').read_text());record={}
with tempfile.TemporaryDirectory(prefix='phase3-bench-') as tmp:
 root=Path(tmp);db=connect(root/'graph.sqlite3');initialize(db)
 try:
  t=time.monotonic();ingest_report=ingest(db,source);record['ingestion_seconds']=time.monotonic()-t
  t=time.monotonic();ingest(db,source);record['repeat_ingestion_seconds']=time.monotonic()-t
  t=time.monotonic();build_context_graph(db,db.execute('select max(year) from papers').fetchone()[0]);record['graph_build_seconds']=time.monotonic()-t
  encoder=LocalEncoder();t=time.monotonic();build_index(db,root/'index',encoder);record['index_construction_seconds']=time.monotonic()-t
  engine=search_index(db,root/'index',encoder,model);verifier=GroundingVerifier(db)
  try:
   durations={k:[] for k in ('encoding','retrieval','ranking','grounding')}
   qs=[x for x in queries.read_text().splitlines() if x.strip()]
   for q in qs*5:
    t=time.monotonic();v=encoder.encode([q])[0];durations['encoding'].append((time.monotonic()-t)*1000)
    t=time.monotonic();found=engine.retrieve(q,v);durations['retrieval'].append((time.monotonic()-t)*1000)
    t=time.monotonic();scores=score_model(found['features'],model);durations['ranking'].append((time.monotonic()-t)*1000)
    t=time.monotonic();verifier.explain(engine.results(q,found,scores));durations['grounding'].append((time.monotonic()-t)*1000)
   record['component_latency_ms']={k:{'p50':float(np.percentile(v,50)),'p95':float(np.percentile(v,95))} for k,v in durations.items()}
  finally:engine.close()
 finally:db.close()
 t=time.monotonic();run_batch(str(source),str(queries),str(root/'batch.json'));record['batch_end_to_end_seconds']=time.monotonic()-t
 record.update({'scope':'200-paper sample and 20 warm component calls, local CPU; batch includes complete temporary ingestion and index. Not representative of the 266k-paper graph or a load test.','source_sha256':digest_file(source),'model_sha256':digest_file('models/hybrid_ranker.json'),'queries_per_component':20,'peak_rss_mib_process':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
 write_json(out,record);print(json.dumps(record,indent=2))
