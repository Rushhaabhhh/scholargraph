"""One inference path for batch, API serving, and end-to-end measurements."""

from .scoring import score_model


def search(engine, query: str, model: dict, limit=10):
    if not 1 <= limit <= 100:
        raise ValueError('Result limit must be between 1 and 100')
    if model['encoder_sha256'] != engine.encoder.signature:
        raise ValueError('Reranker and semantic encoder differ')
    retrieved = engine.retrieve(query)
    if not retrieved['author_ids']:
        return []
    return engine.results(query, retrieved, score_model(retrieved['features'], model), limit)
