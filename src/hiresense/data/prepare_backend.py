"""Prepare an application graph/index from any local DBLP slice, without labels."""

import os
import shutil
import tempfile
from pathlib import Path

from ..db import connect, initialize
from ..evaluation.split import dataset_digest, export_snapshot
from ..graph.build import build_context_graph
from ..retrieval.encoder import LocalEncoder
from ..retrieval.index import build_index
from .artifacts import write_json
from .ingest import ingest


def prepare_backend(data, output, cutoff_year=None):
    output = Path(output)
    if output.exists():
        raise ValueError('Backend output must be a new directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=output.parent, prefix='.backend-'))
    root = Path(__file__).resolve().parents[3]
    source, graph = None, None
    try:
        source = connect(stage / 'source.sqlite3')
        initialize(source)
        ingestion = ingest(source, data)
        cutoff = cutoff_year if cutoff_year is not None else source.execute('SELECT MAX(year) FROM papers').fetchone()[0]
        if cutoff is None:
            raise ValueError('A dated paper is required to prepare the application graph')
        counts = export_snapshot(source, stage / 'graph.sqlite3', cutoff, dataset_digest(source))
        source.close()
        source = None
        graph = connect(stage / 'graph.sqlite3')
        graph_report = build_context_graph(graph)
        index_report = build_index(graph, stage / 'index', LocalEncoder(root / 'models/minilm'))
        graph.close()
        graph = None
        # The all-period source is a preparation intermediate, not a serving artifact.
        for path in stage.glob('source.sqlite3*'):
            path.unlink()
        configuration = {'graph': 'graph.sqlite3', 'index': 'index', 'session_db': 'sessions.sqlite3',
                         'encoder': os.path.relpath(root / 'models/minilm', output.resolve()),
                         'model': os.path.relpath(root / 'models/expert_ranker.json', output.resolve()),
                         'recordings': os.path.relpath(root / 'recordings/query-intents.json', output.resolve()),
                         'query_provider': 'recorded'}
        write_json(stage / 'backend.json', configuration)
        report = {'source_sha256': ingestion['source_sha256'], 'ingestion': ingestion, 'snapshot': counts,
                  'cutoff_year': cutoff, 'graph': graph_report, 'index': index_report}
        write_json(stage / 'preparation.json', report)
        stage.rename(output)
        return {'config': str(output / 'backend.json'), **report}
    except BaseException:
        if graph:
            graph.close()
        if source:
            source.close()
        shutil.rmtree(stage)
        raise
