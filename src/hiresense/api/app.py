"""FastAPI boundary for search, graph tools, conversations and session memory."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Path as PathParam, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ..assistant.errors import BackendError
from ..assistant.schemas import DecisionRequest, MessageRequest, RevisionRequest, SearchRequest
from ..assistant.service import Assistant
from .runtime import Backend
from .schemas import (ErrorResponse, HealthResponse, Memory, MessageResponse, MutationResponse,
                      ProfileResponse, SearchResponse, SessionResponse)

_LOG = logging.getLogger('hiresense.api')
SessionId = Annotated[str, PathParam(pattern=r'^[a-f0-9]{32}$')]
AuthorId = Annotated[int, PathParam(ge=0, le=9007199254740991)]


def create_app(config_path=None, backend=None):
    @asynccontextmanager
    async def lifespan(app):
        owned = backend is None
        app.state.backend = backend or Backend.load(config_path or os.environ.get('HIRESENSE_CONFIG', 'resources/experiments/backend.json'))
        app.state.assistant = Assistant(app.state.backend)
        _LOG.info('backend_ready papers=%d authors=%d', len(app.state.backend.engine.papers), len(app.state.backend.engine.authors))
        try:
            yield
        finally:
            if owned:
                app.state.backend.close()

    app = FastAPI(title='HireSense API', version='1.0.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None,
                  responses={400: {'model': ErrorResponse}, 404: {'model': ErrorResponse},
                             409: {'model': ErrorResponse}, 422: {'model': ErrorResponse}, 503: {'model': ErrorResponse}})

    @app.middleware('http')
    async def request_log(request: Request, call_next):
        started, request_id = time.monotonic(), uuid.uuid4().hex
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        _LOG.info('request id=%s method=%s route=%s status=%d elapsed_ms=%.2f',
                  request_id, request.method, route, response.status_code, (time.monotonic() - started) * 1000)
        return response

    @app.exception_handler(BackendError)
    async def domain_error(request, error):
        return JSONResponse(status_code=error.status, content={'code': error.code, 'message': error.message})

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse(status_code=error.status_code, content={'code': 'http_error', 'message': 'Endpoint not found' if error.status_code == 404 else 'Request method is not supported'})

    @app.exception_handler(RequestValidationError)
    async def input_error(request, error):
        # Do not echo raw queries, session tokens, or validation inputs into logs/errors.
        return JSONResponse(status_code=422, content={'code': 'invalid_request', 'message': 'Request fields do not match the API schema'})

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        _LOG.error('backend_operation_failed error_type=%s', type(error).__name__)
        return JSONResponse(status_code=503, content={'code': 'backend_unavailable', 'message': 'The operation failed; retry using the same request ID'})

    @app.get('/health', response_model=HealthResponse)
    def health(request: Request):
        runtime = request.app.state.backend
        return {'status': 'ok', 'papers': len(runtime.engine.papers), 'authors': len(runtime.engine.authors),
                'model_version': runtime.model['version'],
                'query_provider': getattr(runtime.understander.provider, 'name', 'fallback')}

    @app.post('/search', response_model=SearchResponse)
    def search(payload: SearchRequest, request: Request):
        runtime = request.app.state.backend
        arguments = payload.model_dump(exclude={'session_id', 'expected_version', 'request_id'})
        with runtime.lock:
            if payload.session_id is None:
                return runtime.search(arguments)
            turn = request.app.state.assistant.search_turn(payload.session_id, arguments, payload.expected_version, payload.request_id)
            if turn['safety']['blocked']:
                raise BackendError('blocked_input', 'Remove embedded instructions from the research query')
            names = ('query', 'retrieval_query', 'results', 'understanding', 'effective_filters', 'applied_decisions',
                     'memory_applied', 'memory', 'request_id')
            return {name: turn[name] for name in names}

    @app.get('/authors/{person_id}', response_model=ProfileResponse)
    def profile(person_id: AuthorId, request: Request):
        runtime = request.app.state.backend
        with runtime.lock:
            return runtime.profile({'person_id': person_id})

    @app.post('/sessions', response_model=SessionResponse)
    def create_session(request: Request):
        return request.app.state.backend.sessions.create()

    @app.get('/sessions/{session_id}/memory', response_model=Memory)
    def memory(session_id: SessionId, request: Request):
        return request.app.state.backend.sessions.read(session_id)

    @app.post('/sessions/{session_id}/messages', response_model=MessageResponse)
    def message(session_id: SessionId, payload: MessageRequest, request: Request):
        return request.app.state.assistant.turn(session_id, payload.message, payload.expected_version, payload.request_id)

    @app.put('/sessions/{session_id}/decisions/{person_id}', response_model=MutationResponse)
    def decision(session_id: SessionId, person_id: AuthorId, payload: DecisionRequest, request: Request):
        return request.app.state.assistant.decision(session_id, person_id, payload)

    @app.delete('/sessions/{session_id}/memory', response_model=MutationResponse)
    def clear(session_id: SessionId, payload: RevisionRequest, request: Request):
        return request.app.state.assistant.clear_memory(session_id, payload)

    @app.delete('/sessions/{session_id}', status_code=204)
    def delete_session(session_id: SessionId, request: Request):
        with request.app.state.backend.lock:
            request.app.state.backend.sessions.delete_session(session_id)
        return Response(status_code=204)

    return app
