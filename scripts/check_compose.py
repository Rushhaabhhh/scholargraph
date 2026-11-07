#!/usr/bin/env python3
"""Exercise the Compose application without credentials using its public API."""
import json
import os
import urllib.request
import uuid

BASE = os.environ.get('SCHOLARGRAPH_CHECK_API_URL', 'http://127.0.0.1:8000').rstrip('/')


def request(path, method='GET', payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def revision(memory):
    return {'expected_version': memory['version'], 'request_id': uuid.uuid4().hex}


health = request('/health')
assert health['status'] == 'ok' and health['query_provider'] == 'local_llm', health
unseen = request('/search', 'POST', {'query': 'distributed storage systems'})
assert unseen['understanding']['provider'] == 'local_llm' and not unseen['understanding']['used_fallback'], unseen['understanding']
session = request('/sessions', 'POST')
sid, memory = session['session_id'], session['memory']
search = request('/search', 'POST', {'query': 'graph neural networks', 'session_id': sid, **revision(memory)})
assert search['results'], search
memory = search['memory']
profile = request(f'/sessions/{sid}/messages', 'POST', {'message': 'profile #1', **revision(memory)})
assert profile['tool_calls'][0]['tool'] == 'get_profile' and profile['profile'], profile
memory = profile['memory']
decision = request(f'/sessions/{sid}/messages', 'POST', {'message': 'shortlist #1', **revision(memory)})
assert decision['memory']['shortlisted_person_ids'], decision
cleared = request(f'/sessions/{sid}/memory', 'DELETE', revision(decision['memory']))
assert not cleared['memory']['shortlisted_person_ids'], cleared
print('Compose health, search, graph assistant, shortlist, and memory deletion passed.')
