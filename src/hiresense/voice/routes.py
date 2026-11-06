"""Raw WAV endpoints avoid persisting audio and keep credentials on the server."""
import asyncio
from fastapi import APIRouter,Request,Response
from pydantic import BaseModel,ConfigDict,Field
from starlette.concurrency import run_in_threadpool
from ..assistant.errors import BackendError
from .service import SpeechService,MAX_AUDIO

class SpeechText(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    text:str=Field(min_length=1,max_length=1600)

def voice_router():
    router=APIRouter(prefix='/voice',tags=['voice'])
    service=SpeechService()
    gate=asyncio.Semaphore(1)
    def session(request):
        identifier=request.headers.get('X-Session-ID','')
        if len(identifier)!=32 or any(c not in '0123456789abcdef' for c in identifier):raise BackendError('session_required','Start a research session before using voice.',401)
        request.app.state.backend.sessions.read(identifier)
    @router.get('/status')
    def status():return service.status()
    async def execute(fn,*args):
        try:
            await asyncio.wait_for(gate.acquire(),10)
        except asyncio.TimeoutError:
            raise BackendError('speech_busy','Voice is busy. Please retry in a moment.',429) from None
        try:
            try:return await asyncio.wait_for(run_in_threadpool(fn,*args),45)
            except asyncio.TimeoutError:raise BackendError('speech_timeout','Voice processing timed out. You can continue with text.',504) from None
        finally:
            gate.release()
    @router.post('/transcribe')
    async def transcribe(request:Request):
        session(request)
        if request.headers.get('content-type','').split(';')[0] not in ('audio/wav','audio/x-wav'):raise BackendError('invalid_audio','Upload PCM WAV audio.',415)
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>MAX_AUDIO:raise BackendError('audio_too_large','Keep recordings under 30 seconds.',413)
            chunks.append(chunk)
        return await execute(service.transcribe,b''.join(chunks))
    @router.post('/speak')
    async def speak(payload:SpeechText,request:Request):
        session(request)
        if not payload.text.strip():raise BackendError('invalid_text','Enter text to speak.',422)
        audio,media=await execute(service.speak,payload.text)
        return Response(audio,media_type=media,headers={'Cache-Control':'no-store'})
    return router
