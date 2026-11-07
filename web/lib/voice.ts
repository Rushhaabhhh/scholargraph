export type VoiceStatus={stt:{provider:string;available:boolean;local:boolean};tts:{provider:string;available:boolean;local:boolean};max_recording_seconds:number;language:string;sample_rate:number};
export type VoiceProvider='local'|'browser';
export interface Recorder {stop:()=>Promise<Blob>;cancel:()=>void}

// Keep synthesis requests within the API limit without silently dropping the
// rest of a long answer. Split at whitespace when possible.
export function speechChunks(text:string,limit=1500):string[]{
 const chunks:string[]=[];let remaining=text.trim();
 while(remaining.length>limit){let end=remaining.lastIndexOf(' ',limit);if(end<limit/2)end=limit;chunks.push(remaining.slice(0,end).trim());remaining=remaining.slice(end).trim()}
 if(remaining)chunks.push(remaining);return chunks;
}

export function wav(samples:Float32Array,inputRate:number):Blob{
 const length=Math.min(480000,Math.floor(samples.length*16000/inputRate));const pcm=new Int16Array(length);
 for(let i=0;i<length;i++){const start=Math.floor(i*inputRate/16000),end=Math.min(samples.length,Math.max(start+1,Math.floor((i+1)*inputRate/16000)));let sum=0;for(let j=start;j<end;j++)sum+=samples[j];pcm[i]=Math.max(-1,Math.min(1,sum/Math.max(1,end-start)))*32767}
 const buffer=new ArrayBuffer(44+length*2);const view=new DataView(buffer);const str=(offset:number,value:string)=>{for(let i=0;i<value.length;i++)view.setUint8(offset+i,value.charCodeAt(i))};str(0,'RIFF');view.setUint32(4,36+length*2,true);str(8,'WAVE');str(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,'data');view.setUint32(40,length*2,true);for(let i=0;i<length;i++)view.setInt16(44+i*2,pcm[i],true);return new Blob([buffer],{type:'audio/wav'});
}

export async function recordAudio(onLevel:(level:number)=>void,onSilence:()=>void):Promise<Recorder>{
 if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone capture requires HTTPS or localhost. You can still type.');
 const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:false,autoGainControl:true}});
 let context:AudioContext|undefined;let source:MediaStreamAudioSourceNode|undefined;let node:AudioWorkletNode|undefined;let ended=false;const chunks:Float32Array[]=[];let speech=false,lastSpeech=performance.now(),started=lastSpeech;
 const cleanup=()=>{node?.disconnect();source?.disconnect();stream.getTracks().forEach(t=>t.stop());void context?.close();onLevel(0)};
 try{context=new AudioContext();await context.audioWorklet.addModule('/audio-recorder.js');await context.resume();source=context.createMediaStreamSource(stream);node=new AudioWorkletNode(context,'scholargraph-recorder');const mute=context.createGain();mute.gain.value=0;node.connect(mute);mute.connect(context.destination);source.connect(node);started=performance.now();lastSpeech=started;
 node.port.onmessage=e=>{if(ended)return;const samples=new Float32Array(e.data);chunks.push(samples);let sum=0;for(const v of samples)sum+=v*v;const rms=Math.sqrt(sum/samples.length);onLevel(Math.min(1,rms*12));const now=performance.now();if(rms>.006){speech=true;lastSpeech=now}if((speech&&now-lastSpeech>1800)||(now-started>30000)){ended=true;onSilence()}};
 return {stop:async()=>{ended=true;const rate=context!.sampleRate;cleanup();const length=chunks.reduce((n,c)=>n+c.length,0);const samples=new Float32Array(length);let at=0;for(const c of chunks){samples.set(c,at);at+=c.length}return wav(samples,rate)},cancel:()=>{ended=true;cleanup()}};
 }catch(e){cleanup();throw e}
}

export interface RecognitionResult {isFinal:boolean;[index:number]:{transcript:string}}
export interface RecognitionEvent {resultIndex:number;results:{length:number;[index:number]:RecognitionResult}}
export interface BrowserRecognition {lang:string;interimResults:boolean;continuous:boolean;onresult:((event:RecognitionEvent)=>void)|null;onerror:((event:{error:string})=>void)|null;onend:(()=>void)|null;start:()=>void;stop:()=>void;abort:()=>void}
export function recognitionConstructor(): (new()=>BrowserRecognition)|undefined {
 const w=window as unknown as {SpeechRecognition?:new()=>BrowserRecognition;webkitSpeechRecognition?:new()=>BrowserRecognition};return w.SpeechRecognition||w.webkitSpeechRecognition;
}
