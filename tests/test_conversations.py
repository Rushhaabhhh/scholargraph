"""Exercise independent conversation storage and real local inference when installed."""
import json
import sqlite3
import tempfile
import threading
import unittest
import httpx
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from hiresense.assistant.errors import BackendError
from hiresense.conversation.routes import router, ROOT, ChatProvider

class Sessions:
    def __init__(self,path): self.path=path
    def read(self,session):
        if session not in ('a'*32,'b'*32): raise BackendError('session_not_found','Session not found',404)
        return {}

class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=FastAPI();self.app.state.backend=SimpleNamespace(sessions=Sessions(str(Path(self.tmp.name)/'state.sqlite')))
        @self.app.exception_handler(BackendError)
        async def handle(request, exc): return JSONResponse(status_code=exc.status,content={'code':exc.code,'message':exc.message})
        self.app.include_router(router());self.client=TestClient(self.app);self.headers={'X-Session-ID':'a'*32}
    def tearDown(self): self.client.close();self.tmp.cleanup()
    def test_history_is_scoped_and_renamed_and_deleted(self):
        item=self.client.post('/conversations',headers=self.headers).json();cid=item['id']
        self.assertEqual(self.client.get('/conversations/'+cid,headers={'X-Session-ID':'b'*32}).status_code,404)
        self.assertEqual(self.client.patch('/conversations/'+cid,headers=self.headers,json={'text':'My notes'}).json()['title'],'My notes')
        self.assertEqual(len(self.client.get('/conversations',headers=self.headers).json()),1)
        self.assertEqual(self.client.delete('/conversations/'+cid,headers=self.headers).status_code,204)
        self.assertEqual(self.client.get('/conversations/'+cid,headers=self.headers).status_code,404)
    def test_history_preview_is_latest_message_and_session_scoped(self):
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        with sqlite3.connect(self.app.state.backend.sessions.path) as db:
            db.executemany('INSERT INTO conversation_messages(conversation_id,role,content) VALUES(?,?,?)',[(cid,'user','A question'),(cid,'assistant','A useful answer')])
        history=self.client.get('/conversations',headers=self.headers).json()
        self.assertEqual(history[0]['preview'],'A useful answer')
        self.assertEqual(self.client.get('/conversations',headers={'X-Session-ID':'b'*32}).json(),[])
    def test_document_upload_is_scoped_and_bounded(self):
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        upload=self.client.post('/conversations/'+cid+'/documents',headers={**self.headers,'X-Document-Name':'notes.txt'},content=b'Research notes')
        self.assertEqual(upload.status_code,201)
        self.assertEqual(self.client.get('/conversations/'+cid,headers=self.headers).json()['documents'][0]['name'],'notes.txt')
        self.assertEqual(self.client.post('/conversations/'+cid+'/documents',headers={**self.headers,'X-Document-Name':'notes.pdf'},content=b'%PDF').status_code,422)
        self.assertEqual(self.client.delete('/conversations/'+cid+'/documents/'+upload.json()['id'],headers=self.headers).status_code,204)
    def test_edit_replaces_later_turns_and_feedback_follows_message(self):
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        with patch('hiresense.conversation.routes.ChatProvider.stream', return_value=iter(['First response'])):
            self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'Original'})
        messages=self.client.get('/conversations/'+cid,headers=self.headers).json()['messages']
        feedback=self.client.post(f'/conversations/{cid}/messages/{messages[1]["id"]}/feedback',headers=self.headers,json={'rating':'helpful'})
        self.assertEqual(feedback.status_code,200)
        self.assertEqual(self.client.get('/conversations/'+cid,headers=self.headers).json()['messages'][1]['rating'],'helpful')
        with patch('hiresense.conversation.routes.ChatProvider.stream', return_value=iter(['Revised response'])):
            self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'Revised','edit_message_id':messages[0]['id']})
        revised=self.client.get('/conversations/'+cid,headers=self.headers).json()['messages']
        self.assertEqual([m['content'] for m in revised],['Revised','Revised response'])
    def test_research_reads_index_without_search_session(self):
        engine=SimpleNamespace(_lexical=lambda query:[(0,1)], papers=[{'id':'p/1','title':'Graph research','year':2020}],paper_authors=[[10]],authors={10:'A Researcher'})
        self.app.state.backend.engine=engine;self.app.state.backend.lock=threading.Lock()
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        captured=[]
        def generate(messages):
            captured.extend(messages)
            yield 'A response grounded in p/1.'
        with patch('hiresense.conversation.routes.ChatProvider.stream',side_effect=generate):
            response=self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'graph research','research':True})
        events=[json.loads(line) for line in response.text.splitlines()]
        self.assertTrue(any(e['type']=='tool' and e['count']==1 for e in events))
        self.assertTrue(any('Graph research' in m['content'] for m in captured))
        queries=[]
        self.app.state.backend.engine._lexical=lambda query:(queries.append(query) or [(0,1)])
        with patch('hiresense.conversation.routes.ChatProvider.stream',side_effect=lambda messages:iter(['Found a paper.'])):
            response=self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'Search for graph research'})
        events=[json.loads(line) for line in response.text.splitlines()]
        self.assertTrue(any(e['type']=='tool' for e in events))
        self.assertEqual(queries,['graph research'])
    def test_remote_tool_selection_and_stream_parsing(self):
        provider=ChatProvider();provider.kind='openai-compatible';provider.key='test';provider.url='https://example.invalid/v1'
        def handler(request):
            payload=json.loads(request.content)
            if payload.get('stream'):
                return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n')
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'t1','type':'function','function':{'name':'lookup_research_records','arguments':'{"query":"graph"}'}}]}}]})
        real_client=httpx.Client
        with patch('hiresense.conversation.routes.httpx.Client',side_effect=lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs)):
            selected=provider.select_tools([{'role':'user','content':'Find graph papers'}])
            self.assertEqual(selected['query'],'graph')
            self.assertEqual(''.join(provider.stream([{'role':'user','content':'Hello'}])),'Hello')
    def test_busy_local_model_returns_a_bounded_error(self):
        provider=ChatProvider();provider.kind='local'
        class BusyLock:
            def acquire(self, timeout):
                self.timeout=timeout
                return False
            def locked(self): return True
        provider.lock=BusyLock()
        with self.assertRaises(BackendError) as error:
            list(provider.stream([{'role':'user','content':'Hello'}]))
        self.assertEqual(error.exception.code,'model_busy')
        self.assertEqual(provider.lock.timeout,30)
        self.assertTrue(provider.status()['busy'])
    def test_long_conversations_store_and_use_model_summary(self):
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        with sqlite3.connect(self.app.state.backend.sessions.path) as db:
            db.executemany('INSERT INTO conversation_messages(conversation_id,role,content) VALUES(?,?,?)',[(cid,'user' if i%2==0 else 'assistant',f'turn {i}') for i in range(14)])
        prompts=[]
        def generate(messages):
            prompts.append(messages)
            yield 'Notes about earlier turns.' if len(prompts)==1 else 'The next answer.'
        with patch('hiresense.conversation.routes.ChatProvider.stream',side_effect=generate):
            result=self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'Continue'})
        self.assertIn('summarizing',result.text)
        self.assertTrue(any('Notes about earlier turns' in m['content'] for m in prompts[-1]))
        with sqlite3.connect(self.app.state.backend.sessions.path) as db:
            self.assertEqual(db.execute('SELECT content FROM conversation_summaries WHERE conversation_id=?',(cid,)).fetchone()[0],'Notes about earlier turns.')
    @unittest.skipUnless((ROOT/'data/models/query-understanding.gguf').is_file(),'Optional local model unavailable')
    def test_local_model_stream_persists_turn(self):
        cid=self.client.post('/conversations',headers=self.headers).json()['id']
        result=self.client.post('/conversations/'+cid+'/messages',headers=self.headers,json={'text':'Say hello briefly.'})
        events=[json.loads(line) for line in result.text.splitlines()]
        self.assertTrue(any(e['type']=='delta' and e['text'] for e in events),events)
        self.assertGreater(sum(e['type']=='delta' for e in events),1)
        self.assertEqual(events[-1]['type'],'done')
        history=self.client.get('/conversations/'+cid,headers=self.headers).json()['messages']
        self.assertEqual([m['role'] for m in history],['user','assistant'])
        self.assertTrue(history[-1]['content'])
