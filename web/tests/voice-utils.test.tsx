import {describe,expect,it} from 'vitest';
import {speechChunks,wav} from '../lib/voice';

describe('voice utilities',()=>{
 it('keeps all words in speech synthesis requests within the server limit',()=>{
  const text=Array.from({length:900},(_,i)=>`word${i}`).join(' ');
  const chunks=speechChunks(text);
  expect(chunks.length).toBeGreaterThan(1);
  expect(chunks.every(chunk=>chunk.length<=1500)).toBe(true);
  expect(chunks.join(' ')).toBe(text);
 });
 it('caps audio at the server maximum and writes a valid WAV header',async()=>{
  const blob=wav(new Float32Array(48000*32),48000);
  const buffer=await new Promise<ArrayBuffer>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result as ArrayBuffer);reader.onerror=()=>reject(reader.error);reader.readAsArrayBuffer(blob)});
  const data=new DataView(buffer);
  expect(data.getUint32(24,true)).toBe(16000);
  expect(data.getUint32(40,true)).toBe(960000);
  expect(blob.size).toBe(960044);
 });
});
