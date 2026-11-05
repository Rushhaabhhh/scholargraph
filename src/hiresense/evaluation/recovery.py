"""Shared rolling-window validation and end-to-end quality diagnostics."""
import json
from pathlib import Path

import numpy as np

from ..data.artifacts import digest_file, title_key
from ..ranking.scoring import score_model
from .metrics import ranking_metrics
from .split import load_queries, assert_no_leakage


def load_window(directory, database):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text())
    labels=directory/'labels.jsonl'
    if digest_file(labels)!=manifest['labels_sha256']:
        raise ValueError('Rolling labels changed after sealing')
    origin=database.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
    cutoff=database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if origin is None or origin[0]!=manifest['source_dataset_sha256'] or int(cutoff[0])!=manifest['window']['cutoff']:
        raise ValueError('Rolling graph and labels have different provenance or cutoff')
    queries=load_queries(labels)
    window=manifest['window']
    if len(queries)!=window['queries'] or any(not window['start']<=q.year<=window['end'] for q in queries):
        raise ValueError('Rolling query count or years differ from plan')
    assert_no_leakage(database,[],queries,window['cutoff'])
    return queries,manifest['labels_sha256']


def merge_training(caches):
    query_ids=set();titles=set()
    for cache in caches:
        for q in cache['queries']:
            if q.query_id in query_ids or title_key(q.text) in titles:
                raise ValueError('Rolling training queries overlap')
            query_ids.add(q.query_id);titles.add(title_key(q.text))
    merged={'queries':sum((c['queries'] for c in caches),[])}
    for key in ('features','author_ids','lexical','dense'):
        merged[key]=np.concatenate([c[key] for c in caches])
    offsets=[0]
    for c in caches:
        offsets.extend((c['offsets'][1:]+offsets[-1]).tolist())
    merged['offsets']=np.asarray(offsets,dtype=np.int64)
    return merged


def discovery_diagnostics(cache,known_ids,model=None,author_papers=None):
    counters={key:0 for key in ('queries','relevant_instances','known_instances','retrieved_instances',
        'queries_with_history','queries_with_candidates','hit_at_1','hit_at_10',
        'no_history_queries','retrieval_miss_queries','reranking_miss_queries')}
    oracle=[];graph_oracle=[];measured=[];mrr_10=[];mrr_400=[]
    history_groups={}
    values=score_model(cache['features'],model) if model is not None else None
    for i,q in enumerate(cache['queries']):
        start,end=cache['offsets'][i:i+2]
        ids=cache['author_ids'][start:end]
        relevant=set(q.relevant_author_ids);known=relevant & known_ids
        hits=relevant & set(ids.tolist())
        ranked=ids[np.lexsort((ids,-values[start:end]))].tolist() if values is not None else ids.tolist()
        metrics=ranking_metrics(ranked,relevant);measured.append(metrics)
        if author_papers is not None:
            top=set(ranked[:10])
            for author in relevant:
                count=len(author_papers.get(author,()))
                band='no_history' if count==0 else 'history_1_or_2' if count<=2 else 'history_3_to_19' if count<20 else 'history_20_plus'
                row=history_groups.setdefault(band,{'relevant':0,'retrieved':0,'top10':0})
                row['relevant']+=1;row['retrieved']+=author in hits;row['top10']+=author in top
        mrr_10.append(ranking_metrics(ranked[:10],relevant)['mrr'])
        mrr_400.append(ranking_metrics(ranked[:400],relevant)['mrr'])
        oracle.append(ranking_metrics(sorted(ids.tolist(),key=lambda a:(a not in relevant,a)),relevant))
        graph_oracle.append(ranking_metrics(sorted(known),relevant))
        counters['queries']+=1;counters['relevant_instances']+=len(relevant)
        counters['known_instances']+=len(known);counters['retrieved_instances']+=len(hits)
        counters['queries_with_history']+=bool(known);counters['queries_with_candidates']+=bool(hits)
        counters['hit_at_1']+=bool(ranked and ranked[0] in relevant)
        counters['hit_at_10']+=bool(set(ranked[:10]) & relevant)
        if not known:counters['no_history_queries']+=1
        elif not hits:counters['retrieval_miss_queries']+=1
        elif metrics['ndcg_at_10']==0:counters['reranking_miss_queries']+=1
    average=lambda rows:{k:float(np.mean([r[k] for r in rows])) if rows else 0 for k in ('ndcg_at_10','mrr')}
    n=max(1,counters['queries'])
    return {'counts':counters,'history_coverage':counters['known_instances']/max(1,counters['relevant_instances']),
        'candidate_recall_all':counters['retrieved_instances']/max(1,counters['relevant_instances']),
        'candidate_recall_known':counters['retrieved_instances']/max(1,counters['known_instances']),
        'query_candidate_success':counters['queries_with_candidates']/n,
        'hit_at_1':counters['hit_at_1']/n,'hit_at_10':counters['hit_at_10']/n,
        'metrics':average(measured),'mrr_at_10':float(np.mean(mrr_10)) if mrr_10 else 0,
        'mrr_at_400':float(np.mean(mrr_400)) if mrr_400 else 0,'candidate_oracle':average(oracle),'graph_oracle':average(graph_oracle),
        'author_history_groups':history_groups,
        'oracle_scope':'Analytical ground-truth ordering upper bounds; not model predictions.'}
