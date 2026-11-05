#!/usr/bin/env python3
"""Export a blinded expert-evidence review pool; never invent human judgments."""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,write_json
from hiresense.db import connect
from hiresense.evaluation.split import load_queries
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.factory import search_index
from hiresense.retrieval.encoder import LocalEncoder

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--training-report',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--queries',type=int,default=30)
a=p.parse_args()
if a.out.exists():raise ValueError('Use a fresh judgment pool')
r=json.loads(a.training_report.read_text());config=r['config'];model=json.loads(Path(r['selected_model']).read_text())
directory=Path(config['source_work'])/config['validation_role']
queries=load_queries(directory/'labels.jsonl')[:a.queries]
db=connect(directory/'graph.sqlite3');engine=None;rows=[]
try:
    engine=search_index(db,directory/'index',LocalEncoder(config['encoder']),model,
                        profiles=directory/'evidence_profiles',cross_directory=config['cross_encoder'])
    for q in queries:
        retrieval=engine.retrieve(q.text);ids=retrieval['author_ids'];values=score_model(retrieval['features'],model)
        learned=[ids[i] for i in np.lexsort((np.asarray(ids),-values))[:10]]
        pooled=set(learned)|set(retrieval['lexical'][:10])|set(retrieval['dense'][:10])
        candidates=[]
        for author in sorted(pooled):
            if author not in retrieval['evidence']:continue
            evidence=[{'title':engine.papers[i]['title'],'year':engine.papers[i]['year'],
                       'paper_id':engine.papers[i]['id'],'source':'dblp'} for i in retrieval['evidence'][author]]
            candidates.append({'candidate_id':author,'name':engine.authors[author],'evidence':evidence,
                               'grade':None,'reviewer_note':'','reviewer_id':None})
        random.Random(hashlib.sha256(q.query_id.encode()).hexdigest()).shuffle(candidates)
        rows.append({'query_id':q.query_id,'research_problem':q.text,'candidates':candidates})
    write_json(a.out,{'scope':'Blinded pooled validation candidates for human debugging review; no labels completed automatically and not an independent final suitability benchmark.',
        'instructions':'Grade suitability 0=no relevant expertise demonstrated, 1=partly relevant, 2=plausible expert, 3=strong expert; leave null if unjudged. Cite evidence in reviewer_note. Authors/ranks/methods from automatic relevance are not shown. Judge historical evidence, not future-paper authorship. This pool is incomplete: record judgment coverage and add missing experts separately.',
        'model_sha256':digest_file(r['selected_model']),'validation_labels_sha256':digest_file(directory/'labels.jsonl'),
        'rows':rows})
finally:
    if engine:engine.close()
    db.close()
print(str(a.out))
