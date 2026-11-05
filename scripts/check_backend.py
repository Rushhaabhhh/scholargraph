#!/usr/bin/env python3
"""Start an owned loopback server, exercise HTTP workflows, and stop it cleanly."""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hiresense.data.artifacts import package_digest, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--startup-timeout', type=float, default=30)
args = parser.parse_args()
if args.out.exists() or args.startup_timeout <= 0:
    raise SystemExit('Use a new report path and a positive startup timeout')
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1', 0))
    port = reservation.getsockname()[1]
command = [sys.executable, '-m', 'hiresense.cli', 'serve', '--config', str(args.config.resolve()), '--port', str(port)]
environment = {'PATH': str(Path(sys.executable).parent) + os.pathsep + os.defpath,
               'PYTHONPATH': str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'}
started = time.monotonic()
statuses, claims = [], []
with tempfile.TemporaryFile(mode='w+') as log:
    process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=log, text=True)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5, trust_env=False) as client:
            while True:
                try:
                    response = client.get('/health')
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if process.poll() is not None or time.monotonic() - started > args.startup_timeout:
                    log.seek(0)
                    raise RuntimeError('Backend did not become ready: ' + log.read()[-2000:])
                time.sleep(0.1)
            startup = time.monotonic() - started
            health = response.json()
            statuses.append({'operation': 'health', 'status': response.status_code})
            session = client.post('/sessions').json()['session_id']
            base = f'/sessions/{session}'
            def call(method, url, body, operation):
                response = client.request(method, url, json=body)
                statuses.append({'operation': operation, 'status': response.status_code})
                if response.status_code != 200:
                    raise RuntimeError(f'{operation}: {response.status_code} {response.text}')
                result = response.json()
                claims.extend(result.get('claims', []))
                return result
            first = call('POST', base + '/messages', {'message': 'search graph neural networks', 'expected_version': 0,
                                                     'request_id': 'smoke-search-0001'}, 'search')
            if not first['results']:
                raise RuntimeError('Smoke-test query returned no experts')
            person = first['results'][0]['person_id']
            decision_body = {'decision': 'shortlist', 'expected_version': first['memory']['version'], 'request_id': 'smoke-decision-0001'}
            saved = call('PUT', base + f'/decisions/{person}', decision_body, 'shortlist')
            retried = call('PUT', base + f'/decisions/{person}', decision_body, 'retry_same_decision')
            if saved != retried:
                raise RuntimeError('Idempotent retry changed the response')
            profile = call('POST', base + '/messages', {'message': 'profile #1', 'expected_version': saved['memory']['version'],
                                                       'request_id': 'smoke-profile-0001'}, 'profile')
            path_checked = False
            for result in first['results']:
                partner = next((item['collaborators'][0]['person_id'] for item in result['evidence'] if item['collaborators'] and item['year'] is not None), None)
                if partner is not None:
                    path = call('POST', base + '/messages', {'message': f"path {result['person_id']} {partner}",
                                                            'expected_version': profile['memory']['version'],
                                                            'request_id': 'smoke-path-0001'}, 'collaboration_path')
                    if not path['path']['person_ids']:
                        raise RuntimeError('Known coauthors had no collaboration path')
                    path_checked = True
                    break
            cleared = call('DELETE', base + '/memory', {'expected_version': saved['memory']['version'],
                                                       'request_id': 'smoke-forget-0001'}, 'delete_memory')
            if cleared['memory']['shortlisted_person_ids'] or cleared['memory']['last_query']:
                raise RuntimeError('Memory deletion did not clear the session')
            response = client.delete(base)
            statuses.append({'operation': 'delete_session', 'status': response.status_code})
            if response.status_code != 204:
                raise RuntimeError('Session deletion failed')
            report = {'command': [str(Path(sys.executable).relative_to(ROOT)) if Path(sys.executable).is_relative_to(ROOT) else sys.executable,
                                  'scripts/check_backend.py', '--config', str(args.config), '--out', str(args.out),
                                  '--startup-timeout', str(args.startup_timeout)],
                      'package_source_sha256': package_digest(), 'health': health, 'http_checks': statuses,
                      'path_checked': path_checked, 'generated_claims': len(claims),
                      'unsupported_claims': sum(not claim['supported'] for claim in claims),
                      'startup_seconds': round(startup, 3), 'elapsed_seconds': round(time.monotonic() - started, 3),
                      'runtime_environment': 'Only PATH, PYTHONPATH and PYTHONDONTWRITEBYTECODE; no API keys.',
                      'network_scope': 'Owned loopback HTTP server; no external service calls.'}
            write_json(args.out, report)
            print(json.dumps(report, indent=2))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
