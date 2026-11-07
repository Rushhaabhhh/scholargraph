"""Bounded offline speech and configurable OpenAI-compatible audio adapters."""
import importlib.util
import base64
import binascii
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import threading
import wave
import httpx
from ..assistant.errors import BackendError

ROOT=Path(__file__).resolve().parents[3]
MAX_AUDIO=1_000_000  # 30 seconds of mono 16kHz signed 16-bit PCM, with header.

class SpeechService:
    def __init__(self, stt=None, tts=None):
        self.stt=stt or os.getenv('SCHOLARGRAPH_STT_PROVIDER','vosk')
        self.piper_path=Path(os.getenv('SCHOLARGRAPH_PIPER_MODEL',str(ROOT/'data/models/piper/en_US-ljspeech-medium.onnx')))
        choice=tts or os.getenv('SCHOLARGRAPH_TTS_PROVIDER','auto')
        piper_ready=(self.piper_path.is_file() and Path(str(self.piper_path)+'.json').is_file()
                     and importlib.util.find_spec('piper') is not None)
        self.tts=('piper' if piper_ready else 'espeak') if choice=='auto' else choice
        self.model_path=Path(os.getenv('SCHOLARGRAPH_VOSK_MODEL',str(ROOT/'data/models/vosk-en')))
        self.base=os.getenv('SCHOLARGRAPH_SPEECH_BASE_URL','https://api.openai.com/v1').rstrip('/')
        self.key=os.getenv('SCHOLARGRAPH_SPEECH_API_KEY','')
        self.gemini_key=os.getenv('GEMINI_API_KEY','')
        self.fallback=SpeechService('vosk','auto') if 'gemini' in (self.stt,self.tts) else None
        self._model=None
        self._voice=None
        self._lock=threading.Lock()

    def status(self):
        local=self.fallback.status() if self.fallback else None
        stt_ready=(self.model_path.joinpath('am/final.mdl').is_file() and importlib.util.find_spec('vosk') is not None) if self.stt=='vosk' else bool(self.key) if self.stt=='openai-compatible' else bool(self.gemini_key or (local and local['stt']['available'])) if self.stt=='gemini' else False
        tts_ready=(self.piper_path.is_file() and Path(str(self.piper_path)+'.json').is_file() and importlib.util.find_spec('piper') is not None) if self.tts=='piper' else bool(shutil.which('espeak-ng') or shutil.which('espeak')) if self.tts=='espeak' else bool(self.key) if self.tts=='openai-compatible' else bool(self.gemini_key or (local and local['tts']['available'])) if self.tts=='gemini' else False
        return {'stt':{'provider':self.stt,'available':stt_ready,'local':self.stt=='vosk'},'tts':{'provider':self.tts,'available':tts_ready,'local':self.tts in ('espeak','piper')},'max_recording_seconds':30,'language':'en','sample_rate':16000}

    @staticmethod
    def validate_wav(data):
        if len(data)>MAX_AUDIO:raise BackendError('audio_too_large','Keep recordings under 30 seconds.',413)
        try:
            with wave.open(io.BytesIO(data),'rb') as f:
                if f.getnchannels()!=1 or f.getsampwidth()!=2 or f.getframerate()!=16000 or f.getcomptype()!='NONE':raise ValueError()
                frames=f.getnframes()
                if not 1600<=frames<=480000:raise ValueError()
                pcm=f.readframes(frames)
                if len(pcm)!=frames*2:raise ValueError()
                return pcm
        except (wave.Error,EOFError,ValueError):
            raise BackendError('invalid_audio','Use 16 kHz mono PCM WAV audio, between 0.1 and 30 seconds.',422) from None

    def transcribe(self,data):
        pcm=self.validate_wav(data)
        if not self.status()['stt']['available']:raise BackendError('speech_unavailable','Speech recognition is unavailable. Use text or another voice provider.',503)
        if self.stt=='gemini':
            try:
                parts=self._gemini(os.getenv('SCHOLARGRAPH_GEMINI_STT_MODEL','gemini-2.5-flash'), {'contents':[{'parts':[{'text':'Transcribe the spoken words exactly. Return only the transcript.'},{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(data).decode('ascii')}}]}]})
                text=''.join(part.get('text','') for part in parts).strip()
                if not text: raise BackendError('no_speech','No clear speech was detected.',422)
                return {'text':text[:4000],'provider':'gemini'}
            except BackendError:
                if self.fallback and self.fallback.status()['stt']['available']: return self.fallback.transcribe(data)
                raise
        if self.stt=='vosk':
            from vosk import Model,KaldiRecognizer,SetLogLevel
            with self._lock:
                if self._model is None:
                    SetLogLevel(-1);self._model=Model(str(self.model_path))
                recognizer=KaldiRecognizer(self._model,16000)
                segments=[]
                # Vosk emits completed segments through Result(); FinalResult()
                # only contains audio since the most recent completed segment.
                for offset in range(0,len(pcm),8000):
                    if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                        segments.append(json.loads(recognizer.Result()).get('text','').strip())
                segments.append(json.loads(recognizer.FinalResult()).get('text','').strip())
                text=' '.join(segment for segment in segments if segment)
        else:
            result=self._request('/audio/transcriptions',files={'file':('recording.wav',data,'audio/wav')},data={'model':os.getenv('SCHOLARGRAPH_STT_MODEL','whisper-1'),'language':'en'})
            try:text=result.json().get('text','').strip()
            except (ValueError,AttributeError):raise BackendError('speech_provider_error','The recognition provider returned an invalid response.',502) from None
        if not text:raise BackendError('no_speech','No clear speech was detected. Try again or type your message.',422)
        return {'text':text[:4000],'provider':self.stt}

    def speak(self,text):
        if not self.status()['tts']['available']:raise BackendError('speech_unavailable','Speech playback is unavailable. The text response is still available.',503)
        if self.tts=='gemini':
            try:
                parts=self._gemini(os.getenv('SCHOLARGRAPH_GEMINI_TTS_MODEL','gemini-2.5-flash-preview-tts'), {'contents':[{'parts':[{'text':text}]}],'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'prebuiltVoiceConfig':{'voiceName':os.getenv('SCHOLARGRAPH_GEMINI_TTS_VOICE','Kore')}}}}})
                encoded=next((part.get('inlineData',{}).get('data') for part in parts if part.get('inlineData',{}).get('data')),None)
                if not encoded or len(encoded)>11_000_000: raise ValueError('Missing audio')
                pcm=base64.b64decode(encoded,validate=True)
                if not pcm or len(pcm)%2: raise ValueError('Invalid PCM')
                output=io.BytesIO()
                with wave.open(output,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(pcm)
                return output.getvalue(),'audio/wav'
            except (ValueError,binascii.Error,BackendError):
                if self.fallback and self.fallback.status()['tts']['available']: return self.fallback.speak(text)
                raise BackendError('speech_provider_error','Speech generation failed. Read the text response or retry.',503) from None
        if self.tts=='piper':
            from piper import PiperVoice
            from piper.config import PiperConfig
            from piper.voice import ESPEAK_DATA_DIR
            import onnxruntime as ort
            with self._lock:
                if self._voice is None:
                    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
                    self._voice=PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(self.piper_path)+'.json').read_text())),
                                           session=ort.InferenceSession(str(self.piper_path),sess_options=options,providers=['CPUExecutionProvider']),espeak_data_dir=ESPEAK_DATA_DIR)
                output=io.BytesIO()
                with wave.open(output,'wb') as wav:self._voice.synthesize_wav(text,wav)
                return output.getvalue(),'audio/wav'
        if self.tts=='espeak':
            binary=shutil.which('espeak-ng') or shutil.which('espeak')
            try:
                result=subprocess.run([binary,'--stdout','-v','en-us','-s','165','--stdin'],input=text.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=True)
            except (subprocess.SubprocessError,OSError):raise BackendError('speech_provider_error','Local speech generation failed. Read the text response or retry.',503) from None
            return result.stdout,'audio/wav'
        response=self._request('/audio/speech',json={'model':os.getenv('SCHOLARGRAPH_TTS_MODEL','tts-1'),'voice':os.getenv('SCHOLARGRAPH_TTS_VOICE','alloy'),'input':text,'response_format':'wav'})
        if not response.content or len(response.content)>8_000_000:raise BackendError('speech_provider_error','The speech provider returned invalid audio.',502)
        return response.content,'audio/wav'

    def _gemini(self,model,payload):
        if not self.gemini_key or not re.fullmatch(r'[A-Za-z0-9._-]+',model):
            raise BackendError('speech_unavailable','Configure a valid Gemini speech model and API key.',503)
        try:
            with httpx.Client(timeout=httpx.Timeout(35,connect=8),follow_redirects=False) as client:
                response=client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',headers={'x-goog-api-key':self.gemini_key},json=payload)
                response.raise_for_status()
                parts=response.json()['candidates'][0]['content']['parts']
                if not isinstance(parts,list) or not all(isinstance(part,dict) for part in parts): raise ValueError('Invalid parts')
                return parts
        except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError):
            raise BackendError('speech_provider_error','The Gemini speech provider could not complete the request.',503) from None

    def _request(self,path,**kwargs):
        try:
            with httpx.Client(timeout=httpx.Timeout(35,connect=8),follow_redirects=False) as client:
                response=client.post(self.base+path,headers={'Authorization':'Bearer '+self.key},**kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException:raise BackendError('speech_timeout','The speech provider timed out. Please retry or use text.',504) from None
        except httpx.HTTPError:raise BackendError('speech_provider_error','The speech provider could not complete the request. Check the server configuration.',502) from None
