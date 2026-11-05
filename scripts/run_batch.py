#!/usr/bin/env python3
"""Run the submission interface from any working directory."""
import argparse
import importlib.util
import os
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

project = Path(__file__).resolve().parents[1]
required_modules = ('numpy', 'onnxruntime', 'tokenizers', 'pydantic', 'threadpoolctl')
if any(importlib.util.find_spec(name) is None for name in required_modules):
    environment_python = project / '.venv/bin/python'
    using_project_environment = Path(sys.prefix).resolve() == (project / '.venv').resolve()
    if environment_python.exists() and not using_project_environment:
        os.execv(str(environment_python), [str(environment_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit('Install the dependencies in requirements.lock before running ./run (see README).')

sys.path.insert(0, str(project / 'src'))
from hiresense.batch import run_batch


def main():
    parser = argparse.ArgumentParser(prog='./run', description='HireSense offline batch pipeline')
    parser.add_argument('--data', required=True)
    parser.add_argument('--queries', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        run_batch(args.data, args.queries, args.out)
    except (OSError, EOFError, ValueError, sqlite3.Error, ET.ParseError) as error:
        parser.exit(1, f'hiresense: {error}\n')


if __name__ == '__main__':
    main()
