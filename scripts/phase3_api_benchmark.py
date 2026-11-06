#!/usr/bin/env python3
"""Measure live loopback API and frontend proxy latency with bounded concurrency."""
import argparse,json,statistics,time,sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import write_json
p=argparse.ArgumentParser();p.add_argument('--api',default='http://127.0.0.1:18018');p.add_argument('--web',default='http://127.0.0.1:13018/api');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():raise ValueError('Use new output')
q=[json.loads(line)['query'] for line in Path('resources/experiments/phase3-human-queries.jsonl').read_text().splitlines()][:20]
def request(base,text):
 start=time.monotonic()
 with httpx.Client(base_url=base,timeout=20,trust_env=False) as c:r=c.post('/search',json={'query':text})
 return {'ms':(time.monotonic()-start)*1000,'status':r.status_code,'results':len(r.json().get('results',[]))}
def summary(rows):
 ts=[x['ms'] for x in rows];return {'requests':len(rows),'errors':sum(x['status']!=200 for x in rows),'p50_ms':float(np.percentile(ts,50)),'p95_ms':float(np.percentile(ts,95)),'scope':'Warm requests, HTTP client creation included; not production-scale load.'}
api=[request(a.api,x) for x in q];web=[request(a.web,x) for x in q[:10]]
with ThreadPoolExecutor(max_workers=4) as pool:concurrent=list(pool.map(lambda text:request(a.api,text),q[:12]))
report={'command':sys.argv,'api_sequential':summary(api),'web_proxy_sequential':summary(web),'api_four_concurrent':summary(concurrent),'caveat':'Local loopback, small sample, warm after startup; not 200 QPS or a production load test.'}
write_json(a.out,report);print(json.dumps(report,indent=2))
