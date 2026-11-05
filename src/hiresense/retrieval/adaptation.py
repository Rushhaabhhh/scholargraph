"""Small supervised query-side residual adapters; paper vectors remain unchanged."""
import hashlib
import json

import numpy as np
from threadpoolctl import threadpool_limits


class QueryAdapter:
    def __init__(self, model, dimensions):
        if model['version']!='query-residual-ridge-v1':
            raise ValueError('Unknown query adapter version')
        self.matrix=np.asarray(model['matrix'],dtype=np.float32)
        self.bias=np.asarray(model['bias'],dtype=np.float32)
        if self.matrix.shape!=(dimensions,dimensions) or self.bias.shape!=(dimensions,) or not np.isfinite(self.matrix).all() or not np.isfinite(self.bias).all():
            raise ValueError('Invalid query adapter dimensions or values')
        self.signature=hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest()

    def transform(self, vector):
        vector=np.asarray(vector,dtype=np.float32)
        if vector.shape!=(len(self.bias),) or not np.isfinite(vector).all():
            raise ValueError('Invalid query vector')
        with threadpool_limits(limits=2,user_api='blas'):
            value=vector+vector @ self.matrix+self.bias
        norm=float(np.linalg.norm(value))
        if norm<1e-9 or not np.isfinite(norm) or not np.isfinite(value).all():
            raise ValueError('Query adapter produced an invalid vector')
        return np.asarray(value/norm,dtype=np.float32)
