"""Voice endpoints enforce limits and share the real assistant session."""
import io
import threading
import time
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend_support import make_backend
from hiresense.api.app import create_app
from hiresense.voice.service import SpeechService


def sample_wav():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(bytes(16000))
    return output.getvalue()


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary, self.backend, self.config = make_backend()
        self.context = TestClient(create_app(backend=self.backend), raise_server_exceptions=False)
        self.client = self.context.__enter__()
        self.session = self.client.post('/sessions').json()['session_id']
        self.headers = {'X-Session-ID': self.session}

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.backend.close()
        self.temporary.cleanup()

    def test_voice_requires_a_session_and_valid_bounded_audio(self):
        self.assertEqual(self.client.post('/voice/speak', json={'text': 'hello'}).status_code, 401)
        headers = {**self.headers, 'Content-Type': 'audio/wav'}
        self.assertEqual(self.client.post('/voice/transcribe', headers=headers, content=b'not audio').status_code, 422)
        self.assertEqual(self.client.post('/voice/transcribe', headers=headers, content=b'x' * 1_000_001).status_code, 413)
        self.assertEqual(self.client.post('/voice/speak', headers=self.headers, json={'text': 'x' * 1601}).status_code, 422)

    def test_transcript_uses_existing_chat_and_voice_output(self):
        with patch.object(SpeechService, 'transcribe', return_value={'text': 'search graph retrieval', 'provider': 'test'}), \
             patch.object(SpeechService, 'speak', return_value=(sample_wav(), 'audio/wav')):
            transcript = self.client.post('/voice/transcribe', headers={**self.headers, 'Content-Type': 'audio/wav'}, content=sample_wav())
            self.assertEqual(transcript.status_code, 200)
            response = self.client.post(f'/sessions/{self.session}/messages', json={
                'message': transcript.json()['text'], 'expected_version': 0, 'request_id': 'voice-test-0001'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['tool_calls'][0]['tool'], 'search_experts')
            speech = self.client.post('/voice/speak', headers=self.headers, json={'text': response.json()['message']})
            self.assertEqual(speech.status_code, 200)
            self.assertEqual(speech.headers['content-type'], 'audio/wav')
            self.assertTrue(speech.content.startswith(b'RIFF'))

    def test_transcription_waits_for_interrupted_speech_to_finish(self):
        started=threading.Event()
        release=threading.Event()
        def slow_speech(_service,_text):
            started.set()
            if not release.wait(5): raise RuntimeError('test speech timed out')
            return sample_wav(),'audio/wav'
        with patch.object(SpeechService,'speak',slow_speech), \
             patch.object(SpeechService,'transcribe',return_value={'text':'hello','provider':'test'}), \
             ThreadPoolExecutor(max_workers=2) as pool:
            speech=pool.submit(self.client.post,'/voice/speak',headers=self.headers,json={'text':'hello'})
            self.assertTrue(started.wait(5))
            transcript=pool.submit(self.client.post,'/voice/transcribe',headers={**self.headers,'Content-Type':'audio/wav'},content=sample_wav())
            time.sleep(.2)
            self.assertFalse(transcript.done(), 'transcription should wait for the speech slot')
            release.set()
            self.assertEqual(speech.result(timeout=10).status_code,200)
            self.assertEqual(transcript.result(timeout=10).status_code,200)


if __name__ == '__main__':
    unittest.main()
