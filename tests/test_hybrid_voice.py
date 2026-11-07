"""Cloud speech adapters preserve local fallback and return playable audio."""
import base64
import io
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch
from hiresense.assistant.errors import BackendError
from hiresense.voice.service import SpeechService


def wav():
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000);audio.writeframes(bytes(3200))
    return output.getvalue()


class HybridVoiceTests(unittest.TestCase):
    def setUp(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY':'test'}, clear=True):
            self.service=SpeechService('gemini','gemini')

    def test_cloud_transcription_and_wav_synthesis(self):
        with patch.object(self.service,'_gemini',return_value=[{'text':'graph learning'}]):
            self.assertEqual(self.service.transcribe(wav()),{'text':'graph learning','provider':'gemini'})
        with patch.object(self.service,'_gemini',return_value=[{'inlineData':{'data':base64.b64encode(bytes(4800)).decode()}}]):
            audio,mime=self.service.speak('hello')
        self.assertEqual(mime,'audio/wav')
        with wave.open(io.BytesIO(audio),'rb') as output:
            self.assertEqual((output.getframerate(),output.getnchannels(),output.getsampwidth()),(24000,1,2))

    def test_cloud_failure_uses_local_speech(self):
        ready={'stt':{'available':True},'tts':{'available':True}}
        with patch.object(self.service,'_gemini',side_effect=BackendError('speech_provider_error','failed',503)), \
             patch.object(self.service.fallback,'status',return_value=ready), \
             patch.object(self.service.fallback,'transcribe',return_value={'text':'local','provider':'vosk'}), \
             patch.object(self.service.fallback,'speak',return_value=(wav(),'audio/wav')):
            self.assertEqual(self.service.transcribe(wav())['provider'],'vosk')
            self.assertTrue(self.service.speak('hello')[0].startswith(b'RIFF'))

    def test_vosk_keeps_completed_segments_when_final_result_is_empty(self):
        class Recognizer:
            def __init__(self,*args): pass
            def AcceptWaveform(self,_): return True
            def Result(self): return '{"text":"recognized words"}'
            def FinalResult(self): return '{"text":""}'
        fake=SimpleNamespace(Model=lambda _:object(),KaldiRecognizer=Recognizer,SetLogLevel=lambda _:None)
        local=SpeechService('vosk','auto')
        with patch.dict('sys.modules',{'vosk':fake}), patch.object(local,'status',return_value={'stt':{'available':True}}):
            self.assertEqual(local.transcribe(wav())['text'],'recognized words')


if __name__=='__main__': unittest.main()
