"""Required offline interface using the same hybrid/reranking service as the API."""

import json
import tempfile
from pathlib import Path

from .contracts import validate_batch_results
from .data.artifacts import write_json
from .data.ingest import ingest
from .db import connect, initialize
from .graph.build import build_context_graph


def run_batch(data: str, queries: str, output: str) -> None:
    from .api.runtime import Backend
    from .assistant.providers import QueryUnderstander, RecordedProvider
    from .assistant.memory import SessionStore
    from .assistant.errors import BackendError
    from .retrieval.encoder import LocalEncoder
    from .retrieval.index import build_index
    from .retrieval.factory import default_model_path, search_index

    data, queries, output = Path(data), Path(queries), Path(output)
    if output.resolve() in {data.resolve(), queries.resolve()}:
        raise ValueError('Output must not overwrite the input data or queries')
    root = Path(__file__).resolve().parents[2]
    model = json.loads(default_model_path().read_text())
    encoder = LocalEncoder(root / 'models/minilm')
    results = []
    with tempfile.TemporaryDirectory(prefix='hiresense-batch-') as temporary:
        database = connect(Path(temporary) / 'batch.sqlite3')
        engine = None
        try:
            initialize(database)
            ingest(database, data)
            latest = database.execute('SELECT MAX(year) FROM papers').fetchone()[0] or 1
            build_context_graph(database, latest)
            directory = Path(temporary) / 'index'
            build_index(database, directory, encoder)
            engine = search_index(database, directory, encoder, model)
            recordings = root / 'recordings/query-intents.json'
            provider = RecordedProvider(recordings) if recordings.exists() else None
            runtime = Backend(database, engine, model, SessionStore(Path(temporary) / 'sessions.sqlite3', engine.manifest['content_sha256']), QueryUnderstander(provider))
            for line in queries.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    try:
                        packet = runtime.search({'query': line.strip()})
                        results.append({'query': line.strip(), 'results': packet['results']})
                    except (BackendError, ValueError) as error:
                        results.append({'query': line.strip(), 'results': [], 'error': getattr(error, 'code', 'invalid_query')})
        finally:
            if engine:
                engine.close()
            database.close()
    validate_batch_results(results)
    write_json(output, results)
