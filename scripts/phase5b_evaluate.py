#!/usr/bin/env python3
"""Evaluate independently supplied judgments; never treat missing evidence as grade 0."""
import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('resources/results')

def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))

def metrics(values, pool):
    """Pool ideal is valid only when all candidates in that query were graded."""
    dcg = sum((2**v-1)/math.log2(i+2) for i,v in enumerate(values))
    ideal = sum((2**v-1)/math.log2(i+2) for i,v in enumerate(sorted(pool, reverse=True)[:10]))
    first = next((i+1 for i,v in enumerate(values) if v>=2),None)
    return {'ndcg_at_10_pooled_ideal':dcg/ideal if ideal else 0.0,
            'precision_at_10':sum(v>=2 for v in values)/10,
            'mrr_at_10':1/first if first else 0.0}

def evaluate(master, submissions, production, private, seed=42, n_bootstrap=5000):
    # Slots and the query/year relationship are defined by the trusted package.
    slots={}; query_metadata={}
    for row in master:
        q,person,slot=row['query_id'],str(row['person_id']),str(row['reviewer_slot'])
        if not q or not person or not slot or not q.startswith(('Q','P')):raise ValueError('Invalid master ID or cohort')
        year=int(row['cutoff_year']);expected=2024 if q.startswith('Q') else 2023
        if year!=expected:raise ValueError('Cohort cutoff mismatch')
        if q in query_metadata and query_metadata[q]!=(row['query'],year):raise ValueError('Inconsistent master query')
        query_metadata[q]=(row['query'],year)
        key=(q,person,slot)
        if key in slots:raise ValueError('Duplicate master review slot')
        slots[key]=row
    assigned=defaultdict(set)
    for q,person,slot in slots:assigned[(q,person)].add(slot)
    results={};seen=set();reviewer_seen=set()
    for row in submissions:
        key=(row.get('query_id',''),str(row.get('person_id','')),str(row.get('reviewer_slot','')))
        if key not in slots:raise ValueError('Unknown query, person or review slot')
        if key in seen:raise ValueError('Duplicate submitted review slot')
        seen.add(key)
        # Prevent accidental joins to altered evidence, query or cutoff.
        for field in ('query','cutoff_year','author_name','evidence'):
            if row.get(field,'') != slots[key].get(field,''):raise ValueError(f'Review {field} differs from master')
        grade=row.get('grade_0_to_3','').strip().upper(); reviewer=row.get('reviewer','').strip(); notes=row.get('notes','').strip()
        if grade not in ('','0','1','2','3','U'):raise ValueError('Grade must be blank, 0–3, or U')
        if grade and not reviewer:raise ValueError('Completed reviews require a reviewer ID')
        if grade=='U' and not notes:raise ValueError('Unable-to-judge reviews require a reason')
        if grade:
            identity=(key[0],key[1],reviewer)
            if identity in reviewer_seen:raise ValueError('Reviewer cannot fill multiple slots for one pair')
            reviewer_seen.add(identity)
        results[key]={'grade':grade,'reviewer':reviewer,'notes':notes}
    if not any(r['grade'] in ('0','1','2','3','U') for r in results.values()):raise ValueError('No completed human judgments supplied')
    counts=Counter();grades={};unresolved=[];agreement=[];disagreements=[]
    for pair,expected_slots in assigned.items():
        entries=[results.get((*pair,slot),{'grade':'','reviewer':'','notes':''}) for slot in sorted(expected_slots)]
        counts.update('blank' if not e['grade'] else 'unable' if e['grade']=='U' else 'graded' for e in entries)
        vals=[int(e['grade']) for e in entries if e['grade'] in ('0','1','2','3')]
        if len(entries)==2 and len(vals)==2:
            agreement.append(vals[0]==vals[1])
            if vals[0]!=vals[1]:disagreements.append({'query_id':pair[0],'person_id':pair[1],'grades':vals})
        if len(vals)==len(entries):grades[pair]=statistics.median(vals)
        else:
            unresolved.append({'query_id':pair[0],'person_id':pair[1], 'status':'unable_to_judge' if any(e['grade']=='U' for e in entries) else 'incomplete',
                               'reasons':[e['notes'] for e in entries if e['grade']=='U']})
    lists={q:{'production':[str(x) for x in ids]} for q,ids in production.items()}
    for row in private:
        if row['stratum']=='A_frozen_model_top10':lists.setdefault(row['query_id'],{}).setdefault('frozen_model',[]).append((int(row['frozen_model_rank']),str(row['person_id'])))
    for q,models in lists.items():
        if q not in query_metadata:raise ValueError('Private results contain unknown query')
        if 'frozen_model' in models:models['frozen_model']=[a for _,a in sorted(models['frozen_model'])]
        if ('production' in models and not q.startswith('Q')) or ('frozen_model' in models and not q.startswith('P')):raise ValueError('Evaluation cohorts cannot be merged')
        for ids in models.values():
            if len(ids)!=10 or len(set(ids))!=10 or any((q,a) not in assigned for a in ids):raise ValueError('Top-ten mapping is incomplete or not in review pool')
    query_results={};
    for q,models in lists.items():
        members=[pair for pair in assigned if pair[0]==q]; pool_complete=all(pair in grades for pair in members)
        pool=[grades[pair] for pair in members if pair in grades];query_results[q]={}
        for model,ids in models.items():
            valid=sum((q,a) in grades for a in ids);score=None
            if valid==10 and pool_complete:score=metrics([grades[(q,a)] for a in ids],pool)
            query_results[q][model]={'judged_top10':valid,'top10_coverage':valid/10,'judged_pool':len(pool),'pool_size':len(members),'pool_complete':pool_complete,'metrics':score}
    summaries={};rng=random.Random(seed)
    for cohort,model in (('Q','production'),('P','frozen_model')):
        rows=[v[model] for q,v in query_results.items() if q.startswith(cohort) and model in v];complete=[x['metrics'] for x in rows if x['metrics'] is not None]
        summary={'queries':len(rows),'fully_judged_queries':len(complete),'coverage':sum(r['judged_top10'] for r in rows)/(10*len(rows)) if rows else None,'metrics':None,'query_bootstrap_95':None}
        # Never publish a complete-case aggregate as the population result.
        if rows and len(complete)==len(rows):
            summary['metrics']={k:statistics.fmean(r[k] for r in complete) for k in complete[0]}
            summary['query_bootstrap_95']={}
            for field in complete[0]:
                values=[r[field] for r in complete];samples=sorted(statistics.fmean(rng.choices(values,k=len(values))) for _ in range(n_bootstrap))
                summary['query_bootstrap_95'][field]=[samples[int(.025*(n_bootstrap-1))],samples[int(.975*(n_bootstrap-1))]]
        summaries[cohort]=summary
    strata=defaultdict(list);proxy=[]
    for row in private:
        key=(row['query_id'],str(row['person_id']));strata[row['stratum']].append(key)
        if key in grades:
            proxy.append({'query_id':key[0],'person_id':key[1],'future_authorship_proxy':int(row['proxy_future_author']),'human_grade':grades[key], 'disagrees_at_grade2':(grades[key]>=2)!=bool(int(row['proxy_future_author']))})
    stratum_summary={}
    for name,pairs in strata.items():
        vals=[grades[p] for p in pairs if p in grades];stratum_summary[name]={'total':len(pairs),'complete':len(vals),'grade_at_least_2_fraction':sum(x>=2 for x in vals)/len(vals) if len(vals)==len(pairs) and vals else None}
    stratum_comparisons={}
    baseline='A_frozen_model_top10'
    for name,pairs in strata.items():
        if name==baseline:continue
        queries=sorted({q for q,_ in pairs});deltas=[]
        for q in queries:
            target=[key for key in pairs if key[0]==q];reference=[key for key in strata[baseline] if key[0]==q]
            if target and reference and all(key in grades for key in target+reference):
                deltas.append(statistics.fmean(grades[key]>=2 for key in target)-statistics.fmean(grades[key]>=2 for key in reference))
        result={'eligible_queries':len(queries),'fully_judged_queries':len(deltas),'mean_difference':None,'query_bootstrap_95':None}
        if queries and len(deltas)==len(queries):
            samples=sorted(statistics.fmean(rng.choices(deltas,k=len(deltas))) for _ in range(n_bootstrap))
            result.update(mean_difference=statistics.fmean(deltas),query_bootstrap_95=[samples[int(.025*(n_bootstrap-1))],samples[int(.975*(n_bootstrap-1))]])
        stratum_comparisons[name+'_minus_A']=result
    proxy_complete=len(proxy)==len(private)
    proxy_summary={'compared':len(proxy),'total':len(private),'disagreements':sum(x['disagrees_at_grade2'] for x in proxy) if proxy_complete else None,'disagreement_fraction':statistics.fmean(x['disagrees_at_grade2'] for x in proxy) if proxy_complete and proxy else None}
    return {'scope':'Human judgments only; cohorts separate; pooled ideal conditional on a completely judged pool. Bootstrap is over queries, not within-query uncertainty.',
            'review_slots':dict(counts),'candidate_pairs':len(assigned),'fully_graded_pairs':len(grades),'grade_distribution':dict(Counter(str(v) for v in grades.values())),
            'reviewer_agreement':{'double_graded_pairs':len(agreement),'exact_agreement':statistics.fmean(agreement) if agreement else None,'disagreements':disagreements},
            'cohorts':summaries,'query_results':query_results,'strata':stratum_summary,'stratum_comparisons':stratum_comparisons,'proxy_summary':proxy_summary,'proxy_comparisons':proxy,'unresolved':unresolved,
            'limitations':['Median of two grades is used provisionally; disagreements should be adjudicated.','Unable-to-judge and missing entries prevent complete query metrics.','P pilot is enriched and does not estimate population frequency.','Ideal DCG is restricted to the fully judged pooled candidates, not all experts.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviews',type=Path,nargs='+',required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--master',type=Path,default=ROOT/'phase5b-blinded-review.csv')
    parser.add_argument('--production',type=Path,default=ROOT/'phase5b-production-results-private.json')
    parser.add_argument('--private',type=Path,default=ROOT/'phase5b-excluded-author-sample.csv')
    args=parser.parse_args()
    if args.out.exists():parser.error('Choose a new output path')
    try:
        report=evaluate(read_csv(args.master),[r for path in args.reviews for r in read_csv(path)],json.loads(args.production.read_text())['queries'],read_csv(args.private))
    except (ValueError,KeyError) as exc:parser.error(str(exc))
    args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Wrote {args.out}: {report["fully_graded_pairs"]}/{report["candidate_pairs"]} fully graded pairs')

if __name__=='__main__':main()
