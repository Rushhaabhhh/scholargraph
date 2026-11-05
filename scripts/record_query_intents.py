#!/usr/bin/env python3
"""Explicit preparation command: record actual local LLM outputs, never runtime I/O."""
import argparse
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hiresense.assistant.providers import LocalLLMProvider, PROMPT_VERSION, SYSTEM_PROMPT
from hiresense.assistant.schemas import QueryIntent
from hiresense.data.artifacts import digest_file, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--model', type=Path, required=True)
parser.add_argument('--queries', type=Path, default=Path('recordings/queries.json'))
parser.add_argument('--out', type=Path, default=Path('recordings/query-intents.json'))
args = parser.parse_args()
model_metadata = json.loads((Path(__file__).resolve().parents[1] / 'recordings/local-model.json').read_text())
provider = LocalLLMProvider(args.model, model_metadata['sha256'])
records = []
for query in json.loads(args.queries.read_text()):
    started = monotonic()
    raw = provider.extract(query)
    try:
        QueryIntent.model_validate_json(raw)
        valid = True
    except ValueError:
        valid = False
    records.append({'query': query, 'raw_output': raw, 'schema_valid': valid,
                    'elapsed_seconds': round(monotonic() - started, 3)})
    print(f'Recorded {len(records)}: schema_valid={valid}', file=sys.stderr, flush=True)
write_json(args.out, {'prompt_version': PROMPT_VERSION, 'system_prompt': SYSTEM_PROMPT,
                     'provenance': {'model': 'Qwen/Qwen2.5-0.5B-Instruct-GGUF',
                                    'revision': '9217f5db79a29953eb74d5343926648285ec7e67',
                                    'model_sha256': digest_file(args.model), 'llama_cpp_python': version('llama-cpp-python'),
                                    'temperature': 0, 'seed': 42, 'max_tokens': 160, 'context_tokens': 2048,
                                    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                                    'method': 'Actual CPU inference with JSON-schema-constrained decoding; outputs are unedited.'},
                     'records': records})
