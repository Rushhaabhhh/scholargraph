#!/usr/bin/env python3
"""Trace one research query from retrieval features to sourced graph evidence."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, package_digest, write_json
from hiresense.db import connect
from hiresense.evaluation.split import dataset_digest
from hiresense.ranking.scoring import score_model
from hiresense.retrieval.encoder import LocalEncoder
from hiresense.retrieval.index import FEATURE_NAMES, SearchIndex


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-db', 'graph-db', 'index', 'model', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--query', required=True)
    args = parser.parse_args()
    if args.out.exists() or not args.source_db.is_file() or not args.graph_db.is_file():
        parser.error('Input databases must exist and output must be a new path')
    source, graph = connect(args.source_db), connect(args.graph_db)
    engine = None
    try:
        metadata = graph.execute("SELECT value FROM metadata WHERE key='source_dataset_sha256'").fetchone()
        if metadata is None or metadata[0] != dataset_digest(source):
            raise ValueError('Source database does not match graph provenance')
        model, encoder = json.loads(args.model.read_text()), LocalEncoder()
        engine = SearchIndex(graph, args.index, encoder)
        if model['encoder_sha256'] != encoder.signature:
            raise ValueError('Reranker and encoder differ')
        retrieved = engine.retrieve(args.query)
        if not retrieved['author_ids']:
            raise ValueError('Query returned no candidates')
        scores = score_model(retrieved['features'], model)
        results = engine.results(args.query, retrieved, scores, limit=3)
        feature_rows = {author: row for author, row in zip(retrieved['author_ids'], retrieved['features'])}
        rows = []
        for result in results:
            author = result['person_id']
            rows.append({'person_id': author, 'name': result['name'], 'ranking_score': result['score'],
                         'hybrid_candidate_rank': retrieved['author_ids'].index(author) + 1,
                         'features': {name: float(value) for name, value in zip(FEATURE_NAMES, feature_rows[author])},
                         'evidence': result['evidence']})
        top, paper = results[0], results[0]['evidence'][0]
        original = source.execute('SELECT id,title,year,venue,source FROM papers WHERE id=?', (paper['paper_id'],)).fetchone()
        if original is None or original['title'] != paper['title'] or original['year'] != paper['year']:
            raise ValueError('Evidence differs from source publication')
        authors = [dict(row) for row in graph.execute('''SELECT a.id,a.source_key,a.canonical_name,pa.author_position
            FROM paper_authors pa JOIN authors a ON a.id=pa.author_id
            WHERE pa.paper_id=? ORDER BY pa.author_position''', (paper['paper_id'],))]
        source_authors = [tuple(row) for row in source.execute('''SELECT author_id,author_position FROM paper_authors
            WHERE paper_id=? ORDER BY author_position''', (paper['paper_id'],))]
        if [(row['id'], row['author_position']) for row in authors] != source_authors:
            raise ValueError('Graph authorship differs from the source publication')
        if top['person_id'] not in {row['id'] for row in authors}:
            raise ValueError('Top expert is not an author of the supporting paper')
        edges = [dict(row) for row in graph.execute('''SELECT edge_type,source_id,target_id,edge_year,source_record_id
            FROM context_edges WHERE source_record_id=? ORDER BY edge_type,source_id,target_id''', (paper['paper_id'],))]
        if any(row['edge_year'] != original['year'] or row['source_record_id'] != original['id'] for row in edges):
            raise ValueError('Edge date or provenance differs from the source publication')
        if not any(e['edge_type'] == 'author_paper' and e['source_id'] == f"author:{top['person_id']}" for e in edges):
            raise ValueError('Top expert lacks a sourced author-paper edge')
        report = {'scope': 'Illustrative query and evidence trace, not a model-quality evaluation.',
                  'query': args.query, 'graph_cutoff_year': engine.anchor_year,
                  'graph_papers': len(engine.papers), 'graph_authors': len(engine.authors),
                  'candidate_count': len(retrieved['author_ids']), 'paper_limit': engine.paper_limit,
                  'candidate_limit': engine.candidate_limit, 'top_results': rows,
                  'source_publication': dict(original), 'source_paper_graph_authors': authors,
                  'source_paper_graph_edges': edges, 'model_sha256': digest_file(args.model),
                  'index_content_sha256': engine.manifest['content_sha256'],
                  'package_source_sha256': package_digest(), 'command': sys.argv}
        write_json(args.out, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        if engine is not None:
            engine.close()
        source.close()
        graph.close()


if __name__ == '__main__':
    main()
