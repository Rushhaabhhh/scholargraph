#!/usr/bin/env python3
"""Diagnose ranking on identical frozen paper-retrieval candidates, no training."""
import argparse
import json
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.data.artifacts import digest_file, write_json
from hiresense.db import connect
from hiresense.evaluation.metrics import ranking_metrics
from hiresense.evaluation.phase1_retrieval import aggregate_papers, paper_ranks
from hiresense.evaluation.split import assert_no_leakage, load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex


def band(rank):
    if rank is None: return 'not_retrieved'
    for upper, name in ((1,'top_1'),(10,'2_10'),(20,'11_20'),(50,'21_50'),(100,'51_100'),(400,'101_400'),(800,'401_800')):
        if rank <= upper: return name
    raise ValueError('Unexpected candidate position')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists(): raise ValueError('Use a new output path')
    started=time.monotonic();root=Path('data/processed/lean-v1/validation');labels=root/'labels.jsonl';manifest=json.loads((root/'manifest.json').read_text())
    if digest_file(labels)!=manifest['labels_sha256']:raise ValueError('Validation labels do not match')
    queries=load_queries(labels);db=connect(root/'graph.sqlite3');assert_no_leakage(db,queries,[],manifest['cutoff']);encoder=LocalEncoder();model=json.loads(Path('models/hybrid_ranker.json').read_text());index=SearchIndex(db,root/'index',encoder,**model['retrieval'])
    methods=('max_paper','weighted_top3','hybrid','trained','oracle');all_metrics={x:[] for x in methods};times={x:[] for x in methods};positions={'before':{},'after':{}};traces=[];cases=[]
    try:
        for number,query in enumerate(queries,1):
            context=index.candidate_context(query.text);ids=sorted(context['fused'],key=lambda a:(-context['fused'][a],a))[:index.candidate_limit];found=index.assemble(query.text,ids,context);features=found['features'];truth=set(query.relevant_author_ids);candidate=set(ids);known={x for x in truth if index.author_papers.get(x)}
            start=time.perf_counter();score=score_model(features,model);score_by_id=dict(zip(ids,score));trained=sorted(ids,key=lambda a:(-float(score_by_id[a]),a));times['trained'].append((time.perf_counter()-start)*1000)
            orders={'hybrid':ids,'trained':trained,'oracle':sorted(truth&candidate)+sorted(candidate-truth)}
            for method,mode in (('max_paper','max'),('weighted_top3','top3')):
                start=time.perf_counter();order=aggregate_papers(index,context,mode);orders[method]=[a for a in order if a in candidate];times[method].append((time.perf_counter()-start)*1000)
            for method in methods:
                m=ranking_metrics(orders[method][:10],truth);all_metrics[method].append(m)
            before={a:i+1 for i,a in enumerate(ids)};after={a:i+1 for i,a in enumerate(trained)}
            for key,mapping in (('before',before),('after',after)):
                for author in truth:
                    keyband=band(mapping.get(author));positions[key][keyband]=positions[key].get(keyband,0)+1
            oracle=all_metrics['oracle'][-1]['ndcg_at_10'];actual=all_metrics['trained'][-1]['ndcg_at_10']
            row={'query_id':query.query_id,'query':query.text,'relevant_count':len(truth),'known_relevant_count':len(known),'candidate_relevant_count':len(truth&candidate),
                 'relevant_positions':[{'author_id':a,'known':a in known,'before':before.get(a),'after':after.get(a)} for a in sorted(truth)],
                 'ndcg10':actual,'oracle_ndcg10':oracle,'oracle_gap':oracle-actual,'mrr10':all_metrics['trained'][-1]['mrr_at_10'],
                 'method_metrics':{name:all_metrics[name][-1] for name in methods}}
            traces.append(row)
            if truth&candidate:
                relevant=min(truth&candidate,key=lambda a:after[a]);top=trained[0]
                _,strong=paper_ranks(context,index.paper_limit)
                def detail(author):
                    j=before[author]-1;papers=[]
                    for pid in found['evidence'][author]:
                        paper=index.papers[pid];papers.append({'paper_id':paper['id'],'title':paper['title'],'year':paper['year'],'dense_similarity':round(float(context['similarities'][pid]),6),'bm25':round(float(context['lexical_scores'].get(pid,0)),6)})
                    matching=strong.intersection(index.author_papers[author])
                    return {'author_id':author,'name':index.authors[author],'candidate_rank':before[author],'model_rank':after[author],'model_score':float(score[j]),
                            'features':{name:float(value) for name,value in zip(FEATURE_NAMES,features[j])},'historical_publications':len(index.author_papers[author]),
                            'papers_in_top100_of_either_source':len(matching),
                            'latest_source_top100_paper_year':max((index.papers[p]['year'] or 0 for p in matching),default=0) or None,
                            'top_evidence':papers}
                cases.append({'query_id':query.query_id,'query':query.text,'category':'relevant_below_top10' if after[relevant]>10 else 'relevant_in_top10',
                              'top_ranked_unjudged':detail(top) if top not in truth else None,'highest_ranked_labelled':detail(relevant),
                              'caveat':'Unlabelled authors are unjudged, not automatically irrelevant. Title matching and feature magnitudes do not establish expertise.'})
            if (number+1)%50==0: print(f'Diagnosed {number+1}/{len(queries)} queries',flush=True)
        summary={name:{key:statistics.fmean(x[key] for x in all_metrics[name]) for key in ('ndcg_at_10','mrr_at_10','hit_at_10')} for name in methods}
        # Reciprocal rank 1 exactly corresponds to a labelled first result.
        for name in methods:summary[name]['hit_at_1']=sum(x['mrr_at_10']==1 for x in all_metrics[name])/len(queries)
        count_known=sum(x['known_relevant_count'] for x in traces);total=sum(x['relevant_count'] for x in traces);hits=lambda k:sum(sum(p['before'] is not None and p['before']<=k for p in row['relevant_positions']) for row in traces)
        chosen=(sorted((x for x in cases if x['category']=='relevant_below_top10'),key=lambda x:x['query_id'])[:24]+
                sorted((x for x in cases if x['category']=='relevant_in_top10'),key=lambda x:x['query_id'])[:6])
        comparisons=[x for x in chosen if x['top_ranked_unjudged']]
        feature_comparison={name:{'top_unjudged_median':statistics.median(c['top_ranked_unjudged']['features'][name] for c in comparisons),'labelled_median':statistics.median(c['highest_ranked_labelled']['features'][name] for c in comparisons)} for name in FEATURE_NAMES} if comparisons else {}
        rng=np.random.default_rng(42);sample=rng.integers(0,len(queries),size=(5000,len(queries)))
        paired={}
        for name in ('max_paper','weighted_top3','hybrid'):
            paired[name]={}
            for metric in ('ndcg_at_10','mrr_at_10','hit_at_10'):
                delta=np.array([a[metric]-b[metric] for a,b in zip(all_metrics['trained'],all_metrics[name])])
                paired[name][metric]={'mean_difference':float(delta.mean()),'bootstrap_95pct':np.quantile(delta[sample].mean(axis=1),[.025,.975]).tolist()}
        report={'scope':'Inspected 2024 development cohort, frozen 2023 graph and identical 800-author candidates. Labels are future authorship proxies; non-authors are unjudged. No model training.',
                'command':sys.argv,'queries':len(queries),'labels_sha256':digest_file(labels),'model_sha256':digest_file('models/hybrid_ranker.json'),'index_content_sha256':index.manifest['content_sha256'],'encoder_sha256':encoder.signature,'graph_cutoff':manifest['cutoff'],
                'positions':positions,'candidate_recall':{str(k):{'all':hits(k)/total,'known':hits(k)/count_known} for k in (100,400,800)},
                'baseline_metrics':summary,'latency_ms':{name:({'p50':float(np.percentile(ts,50)),'p95':float(np.percentile(ts,95))} if ts else None) for name,ts in times.items()},
                'latency_scope':'Ordering only; max/top3 include aggregation across the source pool. Shared candidate retrieval, embedding, and feature assembly excluded; hybrid/oracle time not measured.',
                'feature_medians_in_selected_examples':feature_comparison,'paired_trained_minus_baseline':paired,'inspected_examples':chosen,'per_query':traces,
                'limitations':['The reported features and paper titles support comparison but do not establish whether an author is truly relevant.', 'Selected examples are not a representative labelled relevance set.', 'Top-100 source-paper count is an uncalibrated retrieval signal, not a ground-truth count of topically relevant papers.', 'Oracle uses all proxy-labelled future authors, including those without history.'],
                'elapsed_seconds':round(time.monotonic()-started,3),'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
        write_json(args.out,report);print(json.dumps({'metrics':summary,'positions':positions,'examples':len(chosen),'elapsed_seconds':report['elapsed_seconds']},indent=2))
    finally:index.close();db.close()

if __name__=='__main__':main()
