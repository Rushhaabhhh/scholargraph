#!/usr/bin/env python3
"""Compare labelled history coverage of a frozen baseline and historical union.

The extension source is fixed before analysis; labels are used only for coverage.
No graph, index or target-author-conditioned source is built.
"""
import argparse,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hiresense.data.artifacts import digest_file,title_key,write_json
from hiresense.evaluation.split import load_queries

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
if args.out.exists():raise ValueError('Use a new output path')
window=Path('data/processed/lean-v1/validation');manifest=json.loads((window/'manifest.json').read_text());labels=window/'labels.jsonl'
if digest_file(labels)!=manifest['labels_sha256']:raise ValueError('Labels changed')
q=load_queries(labels)
b=sqlite3.connect('file:'+str(window/'graph.sqlite3')+'?mode=ro',uri=True)
e=sqlite3.connect('file:data/processed/recent-history/source.sqlite3?mode=ro',uri=True)
s=sqlite3.connect('file:data/processed/lean-v1/source.sqlite3?mode=ro',uri=True)
b.execute("ATTACH DATABASE 'file:data/processed/recent-history/source.sqlite3?mode=ro' AS ext")
try:
 cutoff=manifest['cutoff'];total=baseline=additional=0; ids=set(); mismatches=[]
 for query in q:
  for author in set(query.relevant_author_ids):
   total+=1
   if b.execute('select exists(select 1 from paper_authors where author_id=?)',(author,)).fetchone()[0]:baseline+=1;continue
   if e.execute('select exists(select 1 from paper_authors pa join papers p on p.id=pa.paper_id where pa.author_id=? and p.year<=?)',(author,cutoff)).fetchone()[0]:
    additional+=1;ids.add(author)
    a=s.execute('select source_key from authors where id=?',(author,)).fetchone();c=e.execute('select source_key from authors where id=?',(author,)).fetchone()
    if not a or not c or a!=c:mismatches.append(author)
 extra=b.execute('select count(*) from ext.papers p left join papers original on original.id=p.id where original.id is null and p.year is not null and p.year<=?',(cutoff,)).fetchone()[0]
 differing=b.execute('select count(*) from papers a join ext.papers b on b.id=a.id where a.content_sha256!=b.content_sha256').fetchone()[0]
 title_conflicts=sum(bool(e.execute('select 1 from papers where title_key=? and year<=?',(title_key(query.text),cutoff)).fetchone()) for query in q)
 if differing:raise ValueError('Shared source paper records differ; union requires resolution')
 result={'scope':'Development coverage only: virtual union of the frozen baseline graph and independently preselected recent-history source, filtered to the same cutoff. No enlarged graph or retrieval index was built.',
 'command':sys.argv,'queries':len(q),'labels_sha256':digest_file(labels),'cutoff':cutoff,'baseline_graph_papers':b.execute('select count(*) from papers').fetchone()[0],
 'extension_source_manifest_sha256':digest_file('data/processed/recent-history/source.xml.manifest.json'),'extension_extra_pre_cutoff_papers':extra,'shared_paper_content_conflicts':differing,
 'extension_query_title_conflicts':title_conflicts,
 'labelled_author_instances':total,'baseline_known':baseline,'additional_known_instances':additional,'union_known':baseline+additional,
 'baseline_coverage':baseline/total,'union_coverage':(baseline+additional)/total,'new_unique_author_ids':len(ids),'source_key_disagreements':len(mismatches),
 'limitations':['Preselected source is a purposeful ML and retrieval venue slice, not all DBLP.', 'Labels are incomplete future-authorship proxies.', 'Source-key checks do not establish human identity.', 'Union coverage does not measure retrieval, latency, ranking or the effect of physically building the graph.']}
 write_json(args.out,result);print(json.dumps(result,indent=2))
finally:b.close();e.close();s.close()
