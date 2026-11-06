'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {Icon} from './Icon';
import {api} from '../lib/api';
import {recordAudio,recognitionConstructor,speechChunks,type BrowserRecognition,type Recorder,type VoiceStatus} from '../lib/voice';

type Phase='idle'|'starting'|'listening'|'transcribing'|'processing'|'speaking'|'completed'|'interrupted'|'error';
const phaseLabel:Record<Phase,string>={idle:'Ready when you are',starting:'Opening microphone',listening:'Listening to you',transcribing:'Transcribing your words',processing:'Preparing a response',speaking:'Speaking the response',completed:'Response complete',interrupted:'Conversation paused',error:'Voice needs attention'};
export function VoiceConsole({session,busy,onSend}:{session:string;busy:boolean;onSend:(text:string,signal?:AbortSignal)=>Promise<string>}){
 const [status,setStatus]=useState<VoiceStatus|null>(null),[provider,setProvider]=useState('server'),[phase,setPhase]=useState<Phase>('idle'),[continuous,setContinuous]=useState(false),[muted,setMuted]=useState(false),[transcript,setTranscript]=useState(''),[error,setError]=useState(''),[level,setLevel]=useState(0),[browserAvailable,setBrowserAvailable]=useState(false),[lastReply,setLastReply]=useState('');
 const recorder=useRef<Recorder|null>(null),recognition=useRef<BrowserRecognition|null>(null),controller=useRef<AbortController|null>(null),audio=useRef<HTMLAudioElement|null>(null),audioUrl=useRef(''),sequence=useRef(0),loop=useRef(false),mutedRef=useRef(false),timer=useRef<ReturnType<typeof setTimeout>|null>(null),mounted=useRef(true),sendRef=useRef(onSend),startRef=useRef<()=>void>(()=>{}),pendingReply=useRef(false),playbackDone=useRef<(()=>void)|null>(null);
 sendRef.current=onSend;mutedRef.current=muted;
 const cleanup=useCallback(()=>{if(timer.current)clearTimeout(timer.current);recorder.current?.cancel();recorder.current=null;const active=recognition.current;recognition.current=null;if(active){active.onend=null;active.onerror=null;active.onresult=null;active.abort()}controller.current?.abort();audio.current?.pause();audio.current=null;playbackDone.current?.();playbackDone.current=null;if(audioUrl.current){URL.revokeObjectURL(audioUrl.current);audioUrl.current=''}if('speechSynthesis'in window)window.speechSynthesis.cancel()},[]);
 useEffect(()=>{mounted.current=true;setBrowserAvailable(Boolean(recognitionConstructor()));const c=new AbortController();api<VoiceStatus>('/voice/status',{signal:c.signal}).then(s=>{if(mounted.current&&!c.signal.aborted){setStatus(s);if(!s.stt.available&&recognitionConstructor())setProvider('browser')}}).catch(()=>{if(mounted.current&&!c.signal.aborted&&recognitionConstructor())setProvider('browser')});return()=>{mounted.current=false;sequence.current++;loop.current=false;c.abort();cleanup()}},[cleanup]);
 const halt=useCallback(()=>{loop.current=false;setContinuous(false);sequence.current++;cleanup();setLevel(0);setPhase('interrupted')},[cleanup]);
 const next=()=>{if(loop.current&&mounted.current)timer.current=setTimeout(()=>startRef.current(),650)};
 async function speak(text:string,token:number){
  if(mutedRef.current||!text)return;
  setPhase('speaking');
  let fallbackText=text;
  if(status?.tts.available){
   const chunks=speechChunks(text);let index=0;
   try{for(;index<chunks.length;index++){
    if(token!==sequence.current||mutedRef.current)return;
    const c=new AbortController();controller.current=c;const timeout=setTimeout(()=>c.abort(),25000);
    try{const response=await fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json','X-Session-ID':session},body:JSON.stringify({text:chunks[index]}),signal:c.signal});if(!response.ok){const e=await response.json().catch(()=>({}));throw new Error(e.message||'Speech playback failed')}
    const blob=await response.blob();if(token!==sequence.current)return;
    audioUrl.current=URL.createObjectURL(blob);const player=new Audio(audioUrl.current);audio.current=player;
    await new Promise<void>((resolve,reject)=>{playbackDone.current=resolve;player.onended=()=>resolve();player.onerror=()=>reject(new Error('Audio could not be played. Read the text response or retry playback.'));player.play().catch(()=>reject(new Error('Playback was blocked. Use “Read last response” to play it.')))});playbackDone.current=null;
    }finally{clearTimeout(timeout);playbackDone.current=null;if(audioUrl.current){URL.revokeObjectURL(audioUrl.current);audioUrl.current=''}audio.current=null}
   }return}
   catch(e){if(token!==sequence.current)return;if(!('speechSynthesis'in window))throw e;fallbackText=chunks.slice(index).join(' ')}
  }
  if('speechSynthesis'in window){
   await new Promise<void>((resolve,reject)=>{const u=new SpeechSynthesisUtterance(fallbackText);u.lang='en-US';u.rate=1;u.onend=()=>resolve();u.onerror=event=>event.error==='canceled'||event.error==='interrupted'?resolve():reject(new Error('Browser speech is unavailable. Use the text response.'));window.speechSynthesis.speak(u)})
  }else throw new Error('Audio playback is unavailable. Your text response is still here.');
 }
 async function submit(text:string,token:number){
  if(token!==sequence.current||!mounted.current)return;
  if(!text.trim()){setError('No speech was detected. Try again or type.');setPhase('error');loop.current=false;setContinuous(false);return}
  setTranscript(text);setPhase('processing');pendingReply.current=true;
  try{const c=new AbortController();controller.current=c;const reply=await sendRef.current(text,c.signal);pendingReply.current=false;if(token!==sequence.current||!mounted.current)return;setLastReply(reply);await speak(reply,token);if(token!==sequence.current)return;setPhase('completed');next()}
  catch(e){pendingReply.current=false;if(token!==sequence.current||!mounted.current)return;setError((e as Error).message);setPhase('error');loop.current=false;setContinuous(false)}
 }
 async function finish(){
  if(phase==='starting'){halt();return}
  const token=sequence.current;
  if(recognition.current){recognition.current.stop();return}
  const active=recorder.current;if(!active)return;recorder.current=null;setPhase('transcribing');
  try{const blob=await active.stop();if(token!==sequence.current)return;const c=new AbortController();controller.current=c;const timeout=setTimeout(()=>c.abort(),45000);
   try{const response=await fetch('/api/voice/transcribe',{method:'POST',headers:{'Content-Type':'audio/wav','X-Session-ID':session},body:blob,signal:c.signal});const result=await response.json();if(!response.ok)throw new Error(result.message||'Transcription failed');if(token===sequence.current)await submit(result.text,token)}finally{clearTimeout(timeout)}
  }catch(e){if(token!==sequence.current)return;setPhase('error');setError((e as Error).name==='AbortError'?'Recognition timed out. Please retry or type.':(e as Error).message);loop.current=false;setContinuous(false)}
 }
 async function start(){
  if(!session||busy||pendingReply.current)return;
  cleanup();const token=++sequence.current;setError('');setTranscript('');setPhase('starting');
  try{if(provider==='browser'){
    const Constructor=recognitionConstructor();if(!Constructor)throw new Error('Browser recognition is unavailable. Select server speech or use text.');const r=new Constructor();recognition.current=r;r.lang='en-US';r.interimResults=true;r.continuous=false;let final='';let partial='';let failed=false;
    r.onresult=e=>{final='';partial='';for(let i=0;i<e.results.length;i++){const value=e.results[i][0].transcript;if(e.results[i].isFinal)final+=value+' ';else partial+=value}if(token===sequence.current)setTranscript(final||partial)};
    r.onerror=e=>{failed=true;if(token!==sequence.current)return;setError(e.error==='not-allowed'?'Microphone permission was denied. Enable it in your browser or use text.':`Browser recognition failed (${e.error}). Try server speech or text.`);setPhase('error');loop.current=false;setContinuous(false)};
    r.onend=()=>{if(token!==sequence.current)return;if(timer.current)clearTimeout(timer.current);recognition.current=null;if(!failed)void submit(final||partial,token)};r.start();timer.current=setTimeout(()=>r.stop(),30000);setPhase('listening');
   }else{
    if(!status?.stt.available)throw new Error('Server speech is unavailable. Run the voice setup or use text.');
    const r=await recordAudio(setLevel,()=>void finish());if(token!==sequence.current){r.cancel();return}recorder.current=r;setPhase('listening');
   }}catch(e){if(token!==sequence.current)return;const name=(e as Error).name;setError(name==='NotAllowedError'?'Microphone permission was denied. Enable it in your browser or use text.':name==='NotFoundError'?'No microphone found. Connect one or use text.':(e as Error).message);setPhase('error');loop.current=false;setContinuous(false)}
 }
 startRef.current=()=>void start();
 const capturing=phase==='listening'||phase==='starting';const working=phase==='transcribing'||phase==='processing';
 return <section className={`voice-console voice-${phase}`} aria-label="Voice conversation"><div className="voice-topline"><span className="mini-label">VOICE INTERFACE</span><select aria-label="Speech recognition provider" value={provider} disabled={capturing||working||phase==='speaking'} onChange={e=>{halt();setProvider(e.target.value)}}><option value="server">{status?.stt.available?`Server · ${status.stt.provider}`:'Server · unavailable'}</option>{browserAvailable&&<option value="browser">Browser recognition</option>}</select></div>
  <div className="voice-stage"><div className="voice-orbit" style={{'--voice-level':level} as React.CSSProperties} aria-hidden="true"><span/><span/><span/><Icon name={capturing?'mic':'message'} size={24}/></div><div><strong role="status">{phaseLabel[phase]}</strong><p>{capturing?'Speak a search or a graph command. Silence finishes the recording.':continuous?'Hands-free turns continue after each spoken response.':'Record a message, or keep the conversation going hands-free.'}</p></div></div>
  {transcript&&<div className="voice-transcript"><span>TRANSCRIPT</span><p>{transcript}</p></div>}
  <div className="voice-actions"><button type="button" className={capturing?'voice-record active':'voice-record'} disabled={!session||working||busy} onClick={()=>capturing?void finish():void start()}><Icon name={capturing?'stop':'mic'} size={16}/>{capturing?'Finish recording':phase==='speaking'?'Interrupt & talk':'Push to talk'}</button><button type="button" className={continuous?'voice-mode active':'voice-mode'} aria-pressed={continuous} disabled={!session||working||busy} onClick={()=>{if(continuous){halt()}else{loop.current=true;setContinuous(true);void start()}}}><Icon name="repeat" size={15}/>Continuous</button><button type="button" className="voice-icon" aria-label={muted?'Unmute spoken responses':'Mute spoken responses'} aria-pressed={muted} onClick={()=>{setMuted(v=>!v);if(!muted){audio.current?.pause();if('speechSynthesis'in window)window.speechSynthesis.cancel();halt();setMuted(true)}}}><Icon name={muted?'volumeOff':'volume'} size={17}/></button><button type="button" className="voice-icon" aria-label="Stop voice conversation" onClick={halt}><Icon name="stop" size={16}/></button></div>
  {lastReply&&<button type="button" className="voice-replay" disabled={capturing||working||busy} onClick={()=>{setMuted(false);mutedRef.current=false;setError('');const token=++sequence.current;void speak(lastReply,token).then(()=>{if(token===sequence.current)setPhase('completed')}).catch(e=>{setError(e.message);setPhase('error')})}}><Icon name="volume" size={13}/>Read last response</button>}
  {error&&<p className="voice-error" role="alert">{error}</p>}
  <p className="voice-privacy">{provider==='browser'?'Browser recognition may use your browser’s online speech service.':status?.stt.local?'Speech recognition runs on this server. Audio is not saved.':'Recognition uses the server-configured speech provider.'} Microphone access starts only when you choose to talk.</p>
 </section>
}
