#!/usr/bin/env python3
"""Load assistant settings from the root .env without evaluating shell code."""
import os
from pathlib import Path
import shlex
import sys

root = Path(__file__).resolve().parents[1]
config = root / '.env'
if config.exists():
    for number, raw in enumerate(config.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not (key.startswith('SCHOLARGRAPH_') or key == 'GEMINI_API_KEY'):
            continue
        try:
            parts = shlex.split(value, comments=True)
        except ValueError as exc:
            raise SystemExit(f'Invalid .env value on line {number}: {exc}') from None
        if len(parts) > 1:
            raise SystemExit(f'Quote .env values containing spaces (line {number}).')
        os.environ.setdefault(key, parts[0] if parts else '')
os.execv(sys.executable, [sys.executable, '-m', 'hiresense.cli', 'serve', *sys.argv[1:]])
