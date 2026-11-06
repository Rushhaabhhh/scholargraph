'use client';
import {useEffect,useRef} from 'react';

// A conceptual evidence field, not a display of live research records.
export function Observatory(){
 const ref=useRef<HTMLCanvasElement>(null);
 useEffect(()=>{
  const canvas=ref.current;if(!canvas)return;
  const ctx=canvas.getContext('2d');if(!ctx)return;
  let width=0,height=0,frame=0,tick=0,last=0,visible=false,paused=false;
  const pointer={x:0,y:0};
  const dots=Array.from({length:110},(_,i)=>({x:((i*67)%109)/108,y:((i*43+17)%107)/106,depth:(i%7)/7,major:i%11===0}));
  const resize=()=>{const r=canvas.getBoundingClientRect();width=r.width;height=r.height;const d=Math.min(devicePixelRatio||1,2);canvas.width=width*d;canvas.height=height*d;ctx.setTransform(d,0,0,d,0,0)};
  const draw=(time:number)=>{
   frame=0;if(!visible||document.hidden)return;
   if(time-last<32&&!paused){frame=requestAnimationFrame(draw);return}last=time;
   if(!paused)tick+=.006;
   ctx.clearRect(0,0,width,height);
   const glow=ctx.createRadialGradient(width*.56,height*.47,0,width*.56,height*.47,width*.55);
   glow.addColorStop(0,'rgba(32,89,125,.25)');glow.addColorStop(.45,'rgba(45,44,99,.15)');glow.addColorStop(1,'rgba(4,12,21,0)');ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
   // Three parallel evidence layers create spatial depth without implying live data.
   for(let layer=0;layer<3;layer++){
    const off=(layer-1)*height*.13;ctx.save();ctx.translate(width*.52+pointer.x*8,height*.48+off+pointer.y*6);ctx.transform(1,-.24,.52,.55,0,0);
    ctx.strokeStyle=`rgba(${layer===1?'118,181,202':'114,132,175'},${layer===1?.20:.09})`;ctx.lineWidth=1;
    for(let x=-3;x<=3;x++){ctx.beginPath();ctx.moveTo(x*width*.115,-height*.29);ctx.lineTo(x*width*.115,height*.29);ctx.stroke()}
    for(let y=-2;y<=2;y++){ctx.beginPath();ctx.moveTo(-width*.35,y*height*.13);ctx.lineTo(width*.35,y*height*.13);ctx.stroke()}
    ctx.strokeStyle='rgba(128,169,189,.17)';ctx.strokeRect(-width*.35,-height*.27,width*.7,height*.54);ctx.restore();
   }
   const project=(p:typeof dots[number])=>({x:width*(.2+p.x*.66)+pointer.x*p.depth*12,y:height*(.23+p.y*.49)+(p.x-.5)*height*-.18+pointer.y*p.depth*8});
   const points=dots.map(project);
   for(let i=0;i<dots.length;i++){
    const a=points[i];if(i%3===0){const b=points[(i*7+19)%dots.length];if(Math.hypot(a.x-b.x,a.y-b.y)<width*.24){ctx.strokeStyle='rgba(99,180,204,.13)';ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}}
    const p=dots[i];ctx.fillStyle=p.major?'#c1e7dc':`rgba(113,198,218,${.25+p.depth*.48})`;ctx.beginPath();ctx.arc(a.x,a.y,p.major?2.5:1.05,0,Math.PI*2);ctx.fill();
   }
   // Moving packets follow independent paths across the conceptual network.
   for(let i=0;i<8;i++){
    const t=(tick*.12+i/8)%1,x=width*(.12+t*.73),y=height*(.61-Math.sin(t*Math.PI)*.22)+(i%3-1)*14;
    ctx.fillStyle=`rgba(165,226,227,${Math.sin(t*Math.PI)*.9})`;ctx.fillRect(x,y,6,2);
   }
   if(!paused)frame=requestAnimationFrame(draw);
  };
  const schedule=()=>{if(frame)cancelAnimationFrame(frame);frame=requestAnimationFrame(draw)};
  const motion=()=>{paused=document.documentElement.dataset.motion==='paused'||matchMedia('(prefers-reduced-motion: reduce)').matches;schedule()};
  const observer=new IntersectionObserver(e=>{visible=e[0].isIntersecting;schedule()},{threshold:.05});observer.observe(canvas);
  const size=new ResizeObserver(()=>{resize();schedule()});size.observe(canvas);
  const move=(e:PointerEvent)=>{const r=canvas.getBoundingClientRect();pointer.x=(e.clientX-r.left)/r.width-.5;pointer.y=(e.clientY-r.top)/r.height-.5;if(paused)schedule()};
  const visibility=()=>schedule();canvas.addEventListener('pointermove',move);document.addEventListener('visibilitychange',visibility);window.addEventListener('scholargraph-motion',motion);resize();motion();
  return()=>{cancelAnimationFrame(frame);observer.disconnect();size.disconnect();canvas.removeEventListener('pointermove',move);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('scholargraph-motion',motion)};
 },[]);
 return <canvas ref={ref} className="observatory-canvas" aria-hidden="true"/>;
}
