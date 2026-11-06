"""Multi-turn server orchestration. Source text and LLM outputs never select tools."""

import re
from pydantic import ValidationError

from .errors import BackendError
from .memory import request_digest
from .safety import injection_like, normalized_text
from .schemas import DecisionRequest, MessageRequest, PathArgs, ProfileArgs, RevisionRequest, SearchExpertsArgs

_REF = r'(#[1-9]\d?|[0-9]{1,16}|first|second|third)'


def empty_applied(version):
    return {'version': version, 'shortlisted_person_ids': [], 'rejected_person_ids': [],
            'last_query': None, 'last_intent': None, 'last_result_ids': []}


class Assistant:
    def __init__(self, backend):
        self.backend = backend

    def _person(self, value, memory):
        ordinal = {'first': 1, 'second': 2, 'third': 3}.get(value.lower())
        if value.startswith('#'):
            ordinal = int(value[1:])
        if ordinal is not None:
            if ordinal > len(memory['last_result_ids']):
                raise BackendError('unknown_result_reference', 'Run a search and choose a visible result number')
            identifier = memory['last_result_ids'][ordinal - 1]
        else:
            identifier = int(value)
        try:
            ProfileArgs(person_id=identifier)
        except ValidationError:
            raise BackendError('invalid_person_id', 'Person ID is outside the supported range') from None
        if identifier not in self.backend.engine.authors:
            raise BackendError('author_not_found', 'Author not found', 404)
        return identifier

    def _plan(self, message, memory):
        text = normalized_text(message).strip()
        if injection_like(text):
            return 'blocked', {}
        if re.fullmatch(r'(?:clear|delete|forget)(?: all| my)? (?:memory|decisions)[.!]?', text, re.I):
            return 'clear', {}
        if re.fullmatch(r'(?:show|list)(?: my)? shortlist[.!]?', text, re.I):
            return 'shortlist', {}
        match = re.fullmatch(rf'(shortlist|reject|unshortlist|unreject|clear decision)\s+(?:result\s+)?{_REF}[.!]?', text, re.I)
        if match:
            action = match[1].lower()
            return 'decision', {'person_id': self._person(match[2], memory),
                                'decision': action if action in ('shortlist', 'reject') else 'clear'}
        match = re.fullmatch(rf'(?:show\s+)?(?:profile|publications)(?:\s+(?:of|for))?\s+(?:result\s+)?{_REF}[.!]?', text, re.I)
        if match:
            return 'profile', {'person_id': self._person(match[1], memory)}
        match = re.fullmatch(rf'(?:find\s+)?(?:path|collaboration path)(?:\s+between)?\s+{_REF}\s+(?:and\s+|to\s+)?{_REF}(?:\s+within\s+([0-6])\s+hops?)?[.!]?', text, re.I)
        if match:
            return 'path', {'source': self._person(match[1], memory), 'target': self._person(match[2], memory),
                            'max_hops': int(match[3]) if match[3] is not None else 4}
        if re.fullmatch(r'(?:make it |show |prefer |only )?(?:more )?(?:recent|latest|newest)(?: research| results)?[.!]?', text, re.I):
            if not memory['last_query']:
                raise BackendError('missing_query_context', 'Run a research search before refining it')
            return 'search', {'query': memory['last_query'], 'recency_preference': 'recent'}
        if re.fullmatch(r'(?:any year|all years|no recency preference)[.!]?', text, re.I):
            if not memory['last_query']:
                raise BackendError('missing_query_context', 'Run a research search before refining it')
            return 'search', {'query': memory['last_query'], 'recency_preference': 'any', '_clear_recency': True}
        if re.fullmatch(r'(?:search again|repeat search|show more)[.!]?', text, re.I):
            if not memory['last_query']:
                raise BackendError('missing_query_context', 'Run a research search before repeating it')
            intent = memory['last_intent'] or {}
            return 'search', {'query': memory['last_query'], 'recency_preference': intent.get('recency_preference', 'any'),
                              'since_year': intent.get('since_year')}
        # The remainder of an explicit search is query DATA and is not parsed again.
        match = re.fullmatch(r'(?:search(?: for)?|find experts(?: on| in| for)?)\s+(.+)', text, re.I | re.S)
        if not match:
            return 'unsupported', {}
        query = match[1]
        if len(query) >= 2 and query[0] == query[-1] and query[0] in ('"', "'"):
            query = query[1:-1]
        return 'search', {'query': query}

    def turn(self, session_id, message, expected_version, request_id):
        request = MessageRequest(message=message, expected_version=expected_version, request_id=request_id)
        return self._turn(session_id, request.model_dump(), forced_search=None)

    def search_turn(self, session_id, arguments, expected_version, request_id):
        args = SearchExpertsArgs.model_validate(arguments)
        revision = RevisionRequest(expected_version=expected_version, request_id=request_id)
        payload = {'operation': 'search', **revision.model_dump(), 'arguments': args.model_dump()}
        return self._turn(session_id, payload, forced_search=args.model_dump())

    def _turn(self, session_id, payload, forced_search):
        backend = self.backend
        with backend.lock:
            digest = request_digest(payload)
            cached = backend.sessions.cached(session_id, payload['request_id'], digest)
            if cached is not None:
                return cached
            before = backend.sessions.read(session_id)
            if before['version'] != payload['expected_version']:
                raise BackendError('stale_memory', 'Session changed; read its memory and retry', 409)
            if forced_search is not None:
                action, arguments = ('blocked', {}) if injection_like(forced_search['query']) else ('search', dict(forced_search))
            else:
                action, arguments = self._plan(payload['message'], before)
            calls, context, decision = [], None, None
            response = {'message': '', 'tool_calls': calls, 'memory_applied': before,
                        'provider': 'none', 'safety': {'blocked': action == 'blocked'}, 'results': [], 'claims': []}
            def tool(name, args):
                call = {'tool': name, 'arguments': args, 'outcome': 'success'}
                try:
                    result = backend.execute_tool(name, args, before)
                    calls.append(call)
                    return result
                except (BackendError, ValueError, ValidationError) as error:
                    call['outcome'] = 'error'
                    call['error_code'] = error.code if isinstance(error, BackendError) else 'invalid_tool_arguments'
                    calls.append(call)
                    raise BackendError(call['error_code'], 'The requested graph operation could not be completed') from None
            if action == 'blocked':
                response['message'] = 'Embedded instructions were blocked. Enter a research query or an explicit supported command.'
            elif action == 'unsupported':
                response['message'] = 'I cannot answer that request yet. Try “search graph neural networks”, “profile #1”, or “path #1 #2”. Your search has not changed.'
            elif action == 'clear':
                response['message'] = 'Session decisions and search context were deleted.'
                response['memory_applied'] = empty_applied(before['version'])
            elif action == 'decision':
                decision = (arguments['person_id'], arguments['decision'])
                response['message'] = f"Decision saved: {arguments['decision']} for person {arguments['person_id']}."
            elif action == 'profile':
                profile = tool('get_profile', ProfileArgs.model_validate(arguments).model_dump())
                response.update(profile=profile, claims=profile['claims'], message='Retrieved the sourced publication profile.')
            elif action == 'path':
                path = tool('find_collaboration_path', PathArgs.model_validate(arguments).model_dump())
                response.update(path=path, claims=path['claims'],
                                message='Retrieved a sourced collaboration path.' if path['person_ids'] else 'No path was found within the traversal limits.')
            elif action == 'shortlist':
                profiles = [tool('get_profile', {'person_id': identifier}) for identifier in before['shortlisted_person_ids'][:10]]
                response.update(profiles=profiles, claims=[claim for profile in profiles for claim in profile['claims']],
                                message=f"Showing {len(profiles)} of {len(before['shortlisted_person_ids'])} shortlisted profiles.")
            else:
                clear_recency = arguments.pop('_clear_recency', False)
                # Preserve a prior preference unless explicitly cleared. New topics can still override dates.
                prior = before['last_intent'] or {}
                if clear_recency:
                    intent = before['last_intent'] or {'topics': [arguments['query']]}
                    arguments = {'query': ' '.join(intent['topics']), 'recency_preference': 'any'}
                elif not re.search(r'\b(recent|latest|newest|since|after|from|any year|all years)\b', arguments['query'], re.I):
                    arguments.setdefault('recency_preference', prior.get('recency_preference'))
                    arguments.setdefault('since_year', prior.get('since_year'))
                result = tool('search_experts', SearchExpertsArgs.model_validate(arguments).model_dump())
                response.update(result)
                response['provider'] = result['understanding']['provider']
                response['claims'] = [claim for person in result['results'] for claim in person['claims']]
                response['message'] = f"Found {len(result['results'])} experts with publication evidence." if result['results'] else 'No experts matched the requested filters in this graph.'
                context = {'query': result['query'], 'intent': result['understanding']['intent'],
                           'result_ids': [item['person_id'] for item in result['results']]}
            response['tool_calls'] = calls
            def finish(memory):
                return dict(response, memory=memory, request_id=payload['request_id'])
            return backend.sessions.commit(session_id, payload['expected_version'], payload['request_id'], digest,
                                           finish, context=context, decision=decision, clear=action == 'clear')

    def decision(self, session_id, person_id, request):
        request = DecisionRequest.model_validate(request)
        with self.backend.lock:
            self._person(str(person_id), {})
            payload = {'operation': 'decision', 'person_id': person_id, **request.model_dump()}
            return self.backend.sessions.commit(session_id, request.expected_version, request.request_id, request_digest(payload),
                                               lambda memory: {'memory': memory, 'request_id': request.request_id},
                                               decision=(person_id, request.decision))

    def clear_memory(self, session_id, request):
        request = RevisionRequest.model_validate(request)
        with self.backend.lock:
            payload = {'operation': 'clear_memory', **request.model_dump()}
            return self.backend.sessions.commit(session_id, request.expected_version, request.request_id, request_digest(payload),
                                               lambda memory: {'memory': memory, 'request_id': request.request_id}, clear=True)
