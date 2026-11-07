import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {VoiceConsole} from '../components/VoiceConsole';

const mocks=vi.hoisted(()=>({record:vi.fn(),recognition:vi.fn(),api:vi.fn()}));
vi.mock('../lib/api',()=>({api:mocks.api}));
vi.mock('../lib/voice',async(importOriginal)=>({...await importOriginal<typeof import('../lib/voice')>(),recordAudio:mocks.record,recognitionConstructor:mocks.recognition}));
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});
beforeEach(()=>{
 mocks.api.mockReset().mockResolvedValue({stt:{provider:'vosk',available:true,local:true},tts:{provider:'piper',available:true,local:true}});
 mocks.record.mockReset().mockResolvedValue({stop:async()=>new Blob(['audio'],{type:'audio/wav'}),cancel:vi.fn()});
 mocks.recognition.mockReset().mockReturnValue(class {});
});

it('keeps server recognition selected after an empty recording and gives microphone guidance',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({code:'no_speech',message:'No speech'})}));
 render(<VoiceConsole session="session" busy={false} onSend={vi.fn()}/>);
 await waitFor(()=>expect(mocks.api).toHaveBeenCalled());
 fireEvent.click(screen.getByRole('button',{name:'Push to talk'}));
 fireEvent.click(await screen.findByRole('button',{name:'Finish recording'}));
 expect((await screen.findByRole('alert')).textContent).toContain('microphone');
 expect(screen.getByLabelText('Speech recognition provider')).toHaveProperty('value','server');
});

it('provides an audible voice test and can play the latest answer',async()=>{
 const fetcher=vi.fn().mockResolvedValue({ok:true,blob:async()=>new Blob(['audio'],{type:'audio/wav'})});vi.stubGlobal('fetch',fetcher);
 vi.stubGlobal('Audio',class {onended:(()=>void)|null=null;onerror:(()=>void)|null=null;play(){queueMicrotask(()=>this.onended?.());return Promise.resolve()} pause(){}});
 vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:voice'),revokeObjectURL:vi.fn()});
 render(<VoiceConsole session="session" busy={false} onSend={vi.fn()} latestReply="The answer is here."/>);
 await waitFor(()=>expect(mocks.api).toHaveBeenCalled());
 fireEvent.click(screen.getByRole('button',{name:'Test voice'}));
 await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(1));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Play last answer'})).not.toHaveProperty('disabled',true));
 fireEvent.click(screen.getByRole('button',{name:'Play last answer'}));
 await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));
 expect(JSON.parse(fetcher.mock.calls[1][1].body).text).toBe('The answer is here.');
});

it('sends recognized speech to the assistant and speaks its answer',async()=>{
 const fetcher=vi.fn(async(path:string)=>path.endsWith('/transcribe')?{ok:true,json:async()=>({text:'Explain graph learning'})}:{ok:true,blob:async()=>new Blob(['audio'],{type:'audio/wav'})});vi.stubGlobal('fetch',fetcher);
 vi.stubGlobal('Audio',class {onended:(()=>void)|null=null;play(){queueMicrotask(()=>this.onended?.());return Promise.resolve()} pause(){}});
 vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:voice'),revokeObjectURL:vi.fn()});
 const send=vi.fn().mockResolvedValue('A spoken answer.');
 render(<VoiceConsole session="session" busy={false} onSend={send}/>);
 await waitFor(()=>expect(mocks.api).toHaveBeenCalled());
 fireEvent.click(screen.getByRole('button',{name:'Push to talk'}));
 fireEvent.click(await screen.findByRole('button',{name:'Finish recording'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith('Explain graph learning',expect.any(AbortSignal)));
 await waitFor(()=>expect(fetcher.mock.calls.some(([url])=>url.endsWith('/speak'))).toBe(true));
 expect(screen.getByText('Explain graph learning')).toBeTruthy();
});
