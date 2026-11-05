"""Build the model's declared retrieval pipeline for batch and API serving."""
from pathlib import Path

from .index import SearchIndex

ROOT = Path(__file__).resolve().parents[3]


def default_model_path():
    return ROOT / 'models/hybrid_ranker.json'


def search_index(database, directory, encoder, model, *, profiles=None, cross_directory=None):
    kind = model.get('retrieval_kind')
    if kind not in (None, 'hybrid', 'paper'):
        raise ValueError(f'Unsupported retrieval kind: {kind}')
    if kind in (None, 'paper'):
        return SearchIndex(database, directory, encoder, **model.get('retrieval', {}))
    from .crossencoder import CrossEncoder
    from .hybrid import HybridIndex
    settings = model['retrieval']
    cross = None
    if model.get('use_cross_encoder', True):
        cross = CrossEncoder(cross_directory or ROOT / 'models/crossencoder')
        if cross.signature != model['cross_encoder_sha256']:
            raise ValueError('Cross-encoder differs from the model training artifact')
    return HybridIndex(database, directory, encoder, profiles=profiles or Path(directory) / 'author_profiles',
                       cross_encoder=cross, **settings)
