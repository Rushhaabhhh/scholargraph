"""Pinned local ONNX pair scoring; no network or training dependency at runtime."""
import json
from pathlib import Path

import numpy as np

from ..data.artifacts import digest_file


class CrossEncoder:
    def __init__(self, directory, threads=4):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        directory = Path(directory)
        manifest = json.loads((directory / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            if digest_file(directory / name) != expected:
                raise ValueError(f'Cross-encoder checksum mismatch: {name}')
        self.signature = digest_file(directory / 'manifest.json')
        self.tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=manifest['max_tokens'])
        self.tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        ort.disable_telemetry_events()
        self.session = ort.InferenceSession(str(directory / 'model.onnx'), sess_options=options,
                                           providers=['CPUExecutionProvider'])
        self.inputs = {item.name for item in self.session.get_inputs()}

    def score(self, query, titles, batch_size=16):
        if batch_size < 1:
            raise ValueError('Batch size must be positive')
        output = []
        for offset in range(0, len(titles), batch_size):
            batch = self.tokenizer.encode_batch([(query, title) for title in titles[offset:offset + batch_size]])
            values = {'input_ids': np.asarray([t.ids for t in batch], dtype=np.int64),
                      'attention_mask': np.asarray([t.attention_mask for t in batch], dtype=np.int64),
                      'token_type_ids': np.asarray([t.type_ids for t in batch], dtype=np.int64)}
            logits = self.session.run(None, {key: values[key] for key in self.inputs})[0].reshape(-1)
            if len(logits) != len(batch) or not np.isfinite(logits).all():
                raise ValueError('Invalid cross-encoder output')
            output.extend(logits.tolist())
        return np.asarray(output, dtype=np.float32)
