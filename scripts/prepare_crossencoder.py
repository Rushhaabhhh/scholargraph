#!/usr/bin/env python3
"""Explicit preparation-only download of pinned, verified CPU reranker files."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import digest_file, write_json

REVISION = '233902d25c440f23af6f7d6e94d2946bac0bee0a'
FILES = {
    'model.onnx': ('onnx/model_quint8_avx2.onnx', 'sha256', 'c80a8b34256ea453093d612e3ac48d3d965a0c0a48c7906709af8b8e28461bf9'),
    'tokenizer.json': ('tokenizer.json', 'git-blob', '688882a79f44442ddc1f60d70334a7ff5df0fb47'),
    'model-card.md': ('README.md', 'git-blob', '4c0467b102d751d799638ad2bc0cdf6de56e9745'),
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=ROOT / 'models/crossencoder')
args = parser.parse_args()
if args.out.exists():
    raise SystemExit('Use a new model directory')
args.out.parent.mkdir(parents=True, exist_ok=True)
stage = Path(tempfile.mkdtemp(dir=args.out.parent, prefix='.crossencoder-'))
try:
    for name, (remote, kind, expected) in FILES.items():
        url = f'https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/resolve/{REVISION}/{remote}'
        with urllib.request.urlopen(url, timeout=90) as source, (stage / name).open('wb') as target:
            shutil.copyfileobj(source, target)
        data = (stage / name).read_bytes()
        actual = (hashlib.sha256(data).hexdigest() if kind == 'sha256' else
                  hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest())
        if actual != expected:
            raise ValueError(f'Checksum mismatch for {name}')
    shutil.copy2(ROOT / 'models/minilm/LICENSE', stage / 'LICENSE')
    (stage / 'NOTICE').write_text('cross-encoder/ms-marco-MiniLM-L6-v2, Apache-2.0.\n'
                                 f'Pinned revision: {REVISION}. Quantized AVX2 ONNX inference.\n'
                                 'Pretrained model used unchanged; project author ranker is trained separately.\n')
    write_json(stage / 'manifest.json', {'model': 'cross-encoder/ms-marco-MiniLM-L6-v2', 'revision': REVISION,
                                        'license': 'Apache-2.0', 'max_tokens': 256,
                                        'files': {p.name: digest_file(p) for p in sorted(stage.iterdir())}})
    stage.rename(args.out)
except BaseException:
    shutil.rmtree(stage)
    raise
print(args.out)
