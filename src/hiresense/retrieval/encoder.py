"""Local-only quantized MiniLM inference with masked mean pooling."""

import json
from pathlib import Path

import numpy as np

from ..data.artifacts import digest_file

DEFAULT_ENCODER = Path(__file__).resolve().parents[3] / 'models/minilm'


class LocalEncoder:
    def __init__(self, directory: str | Path = DEFAULT_ENCODER, threads: int = 2):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.directory = Path(directory)
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            if digest_file(self.directory / name) != expected:
                raise ValueError(f'Embedding model checksum mismatch: {name}')
        self.signature = digest_file(self.directory / 'manifest.json')
        self.dimensions = manifest['dimensions']
        self.tokenizer = Tokenizer.from_file(str(self.directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=manifest['max_tokens'])
        self.tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.directory / 'model.onnx'), sess_options=options,
                                           providers=['CPUExecutionProvider'])
        self.input_names = {item.name for item in self.session.get_inputs()}

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        if batch_size < 1:
            raise ValueError('Batch size must be positive')
        output = []
        for offset in range(0, len(texts), batch_size):
            tokens = self.tokenizer.encode_batch(texts[offset:offset + batch_size])
            feeds = {'input_ids': np.asarray([item.ids for item in tokens], dtype=np.int64),
                     'attention_mask': np.asarray([item.attention_mask for item in tokens], dtype=np.int64),
                     'token_type_ids': np.asarray([item.type_ids for item in tokens], dtype=np.int64)}
            hidden = self.session.run(None, {name: feeds[name] for name in self.input_names})[0]
            if hidden.ndim == 3:
                mask = feeds['attention_mask'][..., None].astype(np.float32)
                hidden = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
            hidden = hidden.astype(np.float32)
            hidden /= np.maximum(np.linalg.norm(hidden, axis=1, keepdims=True), 1e-9)
            if hidden.shape[1] != self.dimensions or not np.isfinite(hidden).all():
                raise ValueError('Invalid embedding output')
            output.append(hidden)
        return np.concatenate(output) if output else np.empty((0, self.dimensions), dtype=np.float32)
