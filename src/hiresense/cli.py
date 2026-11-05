"""Offline data commands and the retained graph/ranking prototype commands."""

import argparse
import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from .contracts import DEFAULT_DATABASE, SplitConfig
from .data.artifacts import write_json
from .data.experiment import run_experiment
from .data.ingest import ingest
from .data.noise import generate_noisy_authors
from .data.slice import create_slice
from .db import connect, initialize
from .evaluation.resolution import evaluate_resolution
from .evaluation.split import assert_no_leakage, write_split
from .graph.build import build_context_graph
from .graph.resolution import resolve_records


def _graph_cutoff(database) -> int:
    value = database.execute("SELECT value FROM metadata WHERE key='graph_cutoff_year'").fetchone()
    if value is None:
        raise ValueError('This command requires the graph snapshot (graph.sqlite3) produced by prepare')
    cutoff = int(value[0])
    assert_no_leakage(database, [], [], cutoff)
    return cutoff


def main() -> None:
    parser = argparse.ArgumentParser(prog='hiresense')
    commands = parser.add_subparsers(dest='command', required=True)
    benchmark = commands.add_parser('benchmark', help='Reproduce and measure the 50000-paper data experiment')
    benchmark.add_argument('--config', required=True, type=Path)
    benchmark.add_argument('--out', required=True, type=Path)
    benchmark.add_argument('--report', required=True, type=Path)
    ml = commands.add_parser('ml-benchmark', help='Resolve entities, build retrieval, train and evaluate on temporal labels')
    ml.add_argument('--config', required=True, type=Path)
    backend = commands.add_parser('prepare-backend', help='Prepare a serving graph/index from a local XML slice')
    backend.add_argument('--data', required=True, type=Path)
    backend.add_argument('--out', required=True, type=Path)
    backend.add_argument('--cutoff-year', type=int)
    server = commands.add_parser('serve', help='Start the local backend API')
    server.add_argument('--config', type=Path)
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--port', type=int, default=8000)
    assistant = commands.add_parser('assistant-benchmark', help='Evaluate conversations, grounding and injection resistance')
    assistant.add_argument('--config', type=Path, default=Path('experiments/backend.json'))
    assistant.add_argument('--out', type=Path, required=True)
    assistant.add_argument('--scenarios', type=Path, default=Path('experiments/assistant-scenarios.json'))
    slicer = commands.add_parser('slice', help='Create a reproducible source-order DBLP slice')
    slicer.add_argument('--data', required=True, type=Path)
    slicer.add_argument('--out', required=True, type=Path)
    slicer.add_argument('--limit', type=int, required=True)
    slicer.add_argument('--min-year', type=int, default=1)
    slicer.add_argument('--max-year', type=int, default=9999)
    slicer.add_argument('--types', nargs='+', default=['article', 'inproceedings', 'incollection'])
    slicer.add_argument('--checksum', type=Path)

    for name in ('ingest', 'prepare', 'noise', 'resolve', 'graph', 'index', 'search', 'train', 'evaluate'):
        command = commands.add_parser(name)
        command.add_argument('--db', default=DEFAULT_DATABASE, type=Path)
        if name == 'ingest':
            command.add_argument('--data', required=True, type=Path)
            command.add_argument('--report', type=Path)
        elif name == 'prepare':
            command.add_argument('--cutoff-year', required=True, type=int)
            command.add_argument('--train-end-year', required=True, type=int)
            command.add_argument('--validation-end-year', required=True, type=int)
            command.add_argument('--test-end-year', required=True, type=int)
            command.add_argument('--out', required=True, type=Path)
        elif name == 'noise':
            command.add_argument('--out', required=True, type=Path)
            command.add_argument('--seed', default=42, type=int)
            command.add_argument('--rate', default=0.25, type=float)
        elif name == 'resolve':
            command.add_argument('--noisy', required=True, type=Path)
            command.add_argument('--threshold', default=0.72, type=float)
            command.add_argument('--ambiguity-margin', default=0.06, type=float)
        elif name in ('index', 'search', 'train', 'evaluate'):
            command.add_argument('--encoder', default=Path('models/minilm'), type=Path)
            if name == 'index':
                command.add_argument('--out', required=True, type=Path)
            else:
                command.add_argument('--index', required=True, type=Path)
                command.add_argument('--model', required=True, type=Path)
                if name == 'search':
                    command.add_argument('--query', required=True)
                    command.add_argument('--limit', default=10, type=int)
                else:
                    command.add_argument('--dataset', required=True, type=Path)
                    command.add_argument('--cache', required=True, type=Path)
                    if name == 'evaluate':
                        command.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare-backend':
            from .data.prepare_backend import prepare_backend
            report = prepare_backend(args.data, args.out, args.cutoff_year)
        elif args.command == 'serve':
            import logging
            import uvicorn
            from .api.app import create_app
            logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
            uvicorn.run(create_app(args.config), host=args.host, port=args.port, access_log=False)
            return
        elif args.command == 'assistant-benchmark':
            from .evaluation.assistant import run_assistant_evaluation
            report = run_assistant_evaluation(args.config, args.scenarios, args.out)
        elif args.command == 'ml-benchmark':
            from .evaluation.experiment import run_ml_experiment
            report = run_ml_experiment(args.config)
        elif args.command == 'benchmark':
            report = run_experiment(args.config, args.out, args.report)
        elif args.command == 'slice':
            report = create_slice(args.data, args.out, args.limit, args.min_year, args.max_year, tuple(args.types), args.checksum)
        else:
            if args.command != 'ingest' and not args.db.is_file():
                raise ValueError(f'Database does not exist: {args.db}')
            database = connect(args.db)
            try:
                initialize(database)
                if args.command == 'ingest':
                    if args.report and args.report.resolve() in {args.data.resolve(), args.db.resolve()}:
                        raise ValueError('Report must not overwrite the source data or database')
                    report = ingest(database, args.data)
                    if args.report:
                        write_json(args.report, report)
                elif args.command == 'prepare':
                    config = SplitConfig(args.cutoff_year, args.train_end_year, args.validation_end_year, args.test_end_year)
                    report = write_split(database, args.out, config)
                else:
                    cutoff = _graph_cutoff(database)
                    if args.command == 'noise':
                        report = {'noisy_records': generate_noisy_authors(database, args.out, args.seed, args.rate)}
                    elif args.command == 'resolve':
                        report = resolve_records(database, args.noisy, args.threshold, args.ambiguity_margin)
                        truth = args.noisy.with_suffix('.truth.jsonl')
                        if truth.exists():
                            report['evaluation'] = evaluate_resolution(database, truth)
                    elif args.command == 'graph':
                        report = build_context_graph(database, cutoff)
                    else:
                        from .retrieval.encoder import LocalEncoder
                        from .retrieval.index import SearchIndex, build_index
                        encoder = LocalEncoder(args.encoder)
                        if args.command == 'index':
                            report = build_index(database, args.out, encoder)
                        else:
                            engine = SearchIndex(database, args.index, encoder)
                            try:
                                if args.command == 'search':
                                    from .ranking.service import search
                                    report = search(engine, args.query, json.loads(args.model.read_text()), args.limit)
                                else:
                                    from .evaluation.experiment import train_from_dataset, evaluate_from_dataset
                                    if args.command == 'train':
                                        report = train_from_dataset(engine, args.dataset, args.cache, args.model)
                                    else:
                                        report = evaluate_from_dataset(engine, args.dataset, args.cache, args.model)
                                        write_json(args.out, report)
                            finally:
                                engine.close()
            finally:
                database.close()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    except (OSError, EOFError, ValueError, KeyError, TypeError, sqlite3.Error, ET.ParseError) as error:
        parser.exit(1, f'hiresense: {error}\n')



if __name__ == '__main__':
    main()
