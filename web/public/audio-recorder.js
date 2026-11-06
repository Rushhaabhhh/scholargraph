// PCM is retained only in page memory until the utterance is sent.
class ScholarGraphRecorder extends AudioWorkletProcessor {
 constructor(){super();this.frames=[];this.count=0}
 process(inputs){const channel=inputs[0]?.[0];if(channel){this.frames.push(new Float32Array(channel));this.count+=channel.length;if(this.count>=2048){const data=new Float32Array(this.count);let offset=0;for(const frame of this.frames){data.set(frame,offset);offset+=frame.length}this.port.postMessage(data,[data.buffer]);this.frames=[];this.count=0}}return true}
}
registerProcessor('scholargraph-recorder',ScholarGraphRecorder);
