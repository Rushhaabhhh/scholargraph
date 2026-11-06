#!/usr/bin/env python3
"""Compare bounded candidate-generation methods on a fixed temporal development set."""
import argparse
import json
import math
import resource
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.phase1_retrieval import aggregate_papers, fuse_author_ranks, paper_ranks, topical_neighbors
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import SearchIndex


def profiles(index, path):
    """At most two title-vector clusters over each author's 12 latest papers."""
    ids = sorted(index.author_papers)
    arr = np.lib.format.open_memmap(path, mode='w+', dtype=np.float32, shape=(2 * len(ids), index.encoder.dimensions))
    authors = np.empty(2 * len(ids), dtype=np.int64)
    count = 0
    for author in ids:
        papers = sorted(index.author_papers[author], key=lambda p: (-(index.papers[p]['year'] or 0), index.papers[p]['id']))[:12]
        matrix = np.asarray(index.vectors[papers], dtype=np.float32)
        if len(papers) >= 4:
            second = int(np.argmin(matrix @ matrix[0]))
            clusters = (matrix @ matrix[second]) > (matrix @ matrix[0])
        else:
            clusters = np.zeros(len(papers), dtype=bool)
        for group in (False, True):
            if not np.any(clusters == group):
                continue
            value = matrix[clusters == group].mean(axis=0)
            arr[count] = value / max(float(np.linalg.norm(value)), 1e-9)
            authors[count] = author
            count += 1
    arr.flush()
    return arr, authors[:count], count


def profile_top(vectors, authors, count, query_vector, limit=128):
    with threadpool_limits(limits=2, user_api='blas'):
        scores = np.asarray(vectors[:count] @ query_vector, dtype=np.float32)
    # Each author has at most two rows; 2*limit rows suffice for limit unique authors.
    n = min(count, 2 * limit)
    chosen = np.argpartition(-scores, n-1)[:n] if n else []
    chosen = sorted(chosen, key=lambda i: (-float(scores[i]), int(authors[i]), int(i)))
    output, seen = [], set()
    for row in chosen:
        author = int(authors[row])
        if author not in seen:
            output.append(author); seen.add(author)
            if len(output) == limit: break
    return output


def evaluate(index, context, query, author_order, model):
    truth = set(query.relevant_author_ids)
    known = {a for a in truth if index.author_papers.get(a)}
    candidates = author_order[:800]
    hits = truth.intersection(candidates)
    # New routes may find an author outside paper fusion. They get a zero paper
    # prior; all other pre-existing ranker features retain their original meaning.
    filtered_context = dict(context, fused=dict(context['fused']))
    for author in candidates: filtered_context['fused'].setdefault(author, 0.0)
    retrieved = index.assemble(query.text, candidates, filtered_context)
    score = score_model(retrieved['features'], model)
    ranked = [candidates[i] for i in sorted(range(len(score)), key=lambda i: (-float(score[i]), candidates[i]))]
    return {'total':len(truth), 'known':len(known),
            'hits100':len(truth.intersection(candidates[:100])), 'hits400':len(truth.intersection(candidates[:400])),
            'hits800':len(hits), 'query_hit':int(bool(hits)),
            'oracle_all':ranking_metrics(sorted(hits),truth)['ndcg_at_10'],
            'oracle_known':ranking_metrics(sorted(hits),known)['ndcg_at_10'],
            'ndcg10':ranking_metrics(ranked[:10],truth)['ndcg_at_10'],
            'mrr10':ranking_metrics(ranked[:10],truth)['mrr_at_10'],
            'candidate_ids':candidates}


def summarize(rows, latency):
    n=len(rows); total=sum(x['total'] for x in rows); known=sum(x['known'] for x in rows)
    mean=lambda key: float(np.mean([x[key] for x in rows]))
    return {'author_recall': {str(k):{'all':sum(x[f'hits{k}'] for x in rows)/total,
                                      'known':sum(x[f'hits{k}'] for x in rows)/known} for k in (100,400,800)},
            'retrieved_relevant_instances':sum(x['hits800'] for x in rows),
            'query_hit_at_800':mean('query_hit'), 'candidate_oracle_ndcg10_all':mean('oracle_all'),
            'candidate_oracle_ndcg10_known':mean('oracle_known'), 'candidate_oracle_mrr10_all':mean('query_hit'),
            'candidate_oracle_mrr10_known_queries':sum(x['query_hit'] for x in rows)/sum(x['known']>0 for x in rows),
            'model_ndcg10':mean('ndcg10'), 'model_mrr10':mean('mrr10'),
            'latency_ms':{'p50':float(np.percentile(latency,50)), 'p95':float(np.percentile(latency,95))}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists(): raise ValueError('Use a fresh report path')
    started=time.monotonic(); window=Path('data/processed/lean-v1/validation'); labels=window/'labels.jsonl'
    meta=json.loads((window/'manifest.json').read_text())
    if digest_file(labels)!=meta['labels_sha256']: raise ValueError('Validation labels changed')
    queries=load_queries(labels); database=connect(window/'graph.sqlite3'); assert_no_leakage(database,queries,[],meta['cutoff'])
    model=json.loads(Path('models/hybrid_ranker.json').read_text()); encoder=LocalEncoder()
    index=SearchIndex(database,window/'index',encoder,**model['retrieval'])
    # Serving encodes one query at a time; dynamic padding in batched ONNX
    # inference can slightly alter vectors and candidate ties.
    vectors=np.stack([encoder.encode([q.text])[0] for q in queries]); experiments={}; timings={}; source_rows={};
    try:
        # All aggregation variants at each depth use exactly the same source papers.
        for depth in (1024,2048):
            index.paper_limit=depth
            names=[f'{mode}_{depth}' for mode in ('existing','max','top3','coverage')]
            for name in names:experiments[name]=[];timings[name]=[]
            for i,(query,vector) in enumerate(zip(queries,vectors)):
                start=time.perf_counter();context=index.candidate_context(query.text,vector); retrieval_time=(time.perf_counter()-start)*1000
                paper_scores,_=paper_ranks(context,depth)
                reached={author for paper in paper_scores for author in index.paper_authors[paper]}
                truth=set(query.relevant_author_ids);known={a for a in truth if index.author_papers.get(a)}
                hist={p for a in known for p in index.author_papers[a]}
                if depth not in source_rows:source_rows[depth]=[]
                source_rows[depth].append({'known':len(known),'total':len(truth),'reachable':len(truth&reached),
                                           'historical_papers':len(hist),'retrieved_historical_papers':len(hist.intersection(paper_scores)),
                                           'source_papers':len(paper_scores),'source_authors':len(reached)})
                for mode,name in zip(('existing','max','top3','coverage'),names):
                    t=time.perf_counter()
                    order=(sorted(context['fused'],key=lambda a:(-context['fused'][a],a)) if mode=='existing' else aggregate_papers(index,context,mode))
                    result=evaluate(index,context,query,order,model)
                    experiments[name].append(result);timings[name].append(retrieval_time+(time.perf_counter()-t)*1000)
                if (i+1)%50==0:print(f'depth {depth}: {i+1}/{len(queries)}',flush=True)
        # Development-only selection: maximize known Recall@800; ties prefer less
        # depth, then the baseline, then stronger nDCG. All variants remain in report.
        summaries={name:summarize(rows,timings[name]) for name,rows in experiments.items()}
        selected=max(summaries, key=lambda n:(summaries[n]['author_recall']['800']['known'], -int(n.rsplit('_',1)[1]), summaries[n]['model_ndcg10'], n.startswith('existing')))
        print('Selected paper candidate method for route test:',selected,flush=True)
        mode,depth=selected.rsplit('_',1);index.paper_limit=int(depth)
        with tempfile.TemporaryDirectory(prefix='scholar-topic-profile-') as temporary:
            t=time.perf_counter();profile_vectors, profile_authors, count=profiles(index,Path(temporary)/'vectors.npy');profile_build_seconds=time.perf_counter()-t
            print(f'Built {count} topic profiles in {profile_build_seconds:.1f}s',flush=True)
            for name in ('r1','r2_author_topic','r3_topic_neighbors'):
                experiments[name]=[];timings[name]=[]
            graph_opportunity_instances=0
            for i,(query,vector) in enumerate(zip(queries,vectors)):
                t=time.perf_counter();context=index.candidate_context(query.text,vector)
                paper_order=sorted(context['fused'],key=lambda a:(-context['fused'][a],a)) if mode=='existing' else aggregate_papers(index,context,mode)
                r1time=(time.perf_counter()-t)*1000
                t=time.perf_counter(); author_topics=profile_top(profile_vectors,profile_authors,count,vector);r2=fuse_author_ranks(paper_order,author_topics);r2time=r1time+(time.perf_counter()-t)*1000
                t=time.perf_counter();neighbors=topical_neighbors(index,context,query.text,paper_order);r3=fuse_author_ranks(r2,neighbors,profile_weight=.15);r3time=r2time+(time.perf_counter()-t)*1000
                graph_opportunity_instances+=len((set(query.relevant_author_ids)&set(neighbors))-set(r2[:800]))
                for name,order,cost in (('r1',paper_order,r1time),('r2_author_topic',r2,r2time),('r3_topic_neighbors',r3,r3time)):
                    t=time.perf_counter();experiments[name].append(evaluate(index,context,query,order,model));timings[name].append(cost+(time.perf_counter()-t)*1000)
                if (i+1)%50==0:print(f'profile routes: {i+1}/{len(queries)}',flush=True)
            del profile_vectors
        summaries={name:summarize(rows,timings[name]) for name,rows in experiments.items()}
        # Report paired uncertainty for instance recall with fixed known denominator.
        rng=np.random.default_rng(42);n=len(queries);samples=rng.integers(0,n,size=(5000,n));known=np.array([r['known'] for r in experiments['existing_1024']]);known_total=max(1,int(known.sum()))
        comparisons={}
        for name,rows in experiments.items():
            delta=np.array([a['hits800']-b['hits800'] for a,b in zip(rows,experiments['existing_1024'])]);den=known[samples].sum(axis=1);sample_delta=delta[samples].sum(axis=1)/np.maximum(den,1)
            comparisons[name]={'known_recall800_delta':float(delta.sum()/known_total),'paired_bootstrap_95pct':np.quantile(sample_delta,[.025,.975]).tolist()}
        report={'scope':'Inspected 2024 validation: future authorship is an incomplete relevance proxy; no model was retrained. Raw title queries, pre-cutoff graph; no serving decision, grounding or HTTP.',
                'command':sys.argv,'queries':len(queries),'labels_sha256':digest_file(labels),'graph_cutoff_year':meta['cutoff'],
                'index_content_sha256':index.manifest['content_sha256'],'encoder_sha256':encoder.signature,
                'model_sha256':digest_file('models/hybrid_ranker.json'),'candidate_limit':800,
                'source':{str(depth):{'reachable':sum(x['reachable'] for x in data),'known':sum(x['known'] for x in data),'all':sum(x['total'] for x in data),
                                      'author_recall_known':sum(x['reachable'] for x in data)/sum(x['known'] for x in data),
                                      'paper_recall':sum(x['retrieved_historical_papers'] for x in data)/sum(x['historical_papers'] for x in data),
                                      'paper_recall_scope':'All historical papers authored by labelled people, not individually relevance-labelled.',
                                      'mean_source_papers':float(np.mean([x['source_papers'] for x in data]))} for depth,data in source_rows.items()},
                'variants':summaries,'paired_recall_comparisons_vs_existing_1024':comparisons,'selected_development_method':selected,
                'selection_policy':'Highest known-author Recall@800; tie prefers shallower pool then model nDCG@10.',
                'profile_policy':'At most two normalized local title-vector groups from latest 12 pre-cutoff papers; seed latest and most dissimilar. Top 128 unique authors, RRF weight .25.',
                'graph_policy':'Top 32 paper-route seeds; top 3 historical papers per seed; require cosine >= .4 and query-token overlap in a dated shared paper; add up to 128 collaborators, RRF weight .15.',
                'graph_opportunity_relevant_instances':graph_opportunity_instances,'profile_count':count,'profile_build_seconds':round(profile_build_seconds,3),
                'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'elapsed_seconds':round(time.monotonic()-started,3),
                'latency_scope':'Pre-encoded query; candidate context, aggregation and ranker feature assembly/scoring. Excludes query encoding, HTTP and grounding. Topic profile build excluded.',
                'limitations':['Development selection on the same already inspected cohort; not a held-out estimate.',
                               'Historical author publications are not individually labelled relevant.',
                               'Existing ranker was trained on original retrieval; changed candidates can cause distribution shift.',
                               'Graph-neighbor thresholds and aggregation weights are preliminary and not separately calibrated.',
                               'Memory is process peak RSS and includes the shared graph and encoder; per-variant memory not isolated.']}
        write_json(args.out,report)
        print(json.dumps({k:report[k] for k in ('source','variants','selected_development_method','graph_opportunity_relevant_instances','profile_count','profile_build_seconds','peak_rss_mib','elapsed_seconds')},indent=2),flush=True)
    finally:index.close();database.close()


if __name__=='__main__':main()
