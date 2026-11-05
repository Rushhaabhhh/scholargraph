"""Build the model's declared retrieval pipeline for batch and API serving."""
from pathlib import Path

from .index import SearchIndex

ROOT = Path(__file__).resolve().parents[3]


def default_model_path():
    improved = ROOT / 'models/hybrid_ranker.json'
    return improved if improved.exists() else ROOT / 'models/expert_ranker.json'


def search_index(database, directory, encoder, model, *, profiles=None, cross_directory=None):
    if model.get('retrieval_kind') not in ('hybrid', 'evidence'):
        return SearchIndex(database, directory, encoder)
    from .crossencoder import CrossEncoder
    from .hybrid import HybridIndex
    settings = model['retrieval']
    cross = None
    if model.get('use_cross_encoder', True):
        cross = CrossEncoder(cross_directory or ROOT / 'models/crossencoder')
        if cross.signature != model['cross_encoder_sha256']:
            raise ValueError('Cross-encoder differs from the model training artifact')
    if model.get('retrieval_kind') == 'evidence':
        from .evidence import EvidenceIndex
        return EvidenceIndex(database, directory, encoder, profiles=profiles or Path(directory) / 'evidence_profiles',
                             cross_encoder=cross, query_adapter=model.get('query_adapter'), **settings)
    return HybridIndex(database, directory, encoder, profiles=profiles or Path(directory) / 'author_profiles',
                       cross_encoder=cross, **settings)
