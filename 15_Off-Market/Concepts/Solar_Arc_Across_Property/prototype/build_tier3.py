#!/usr/bin/env python3
import base64, json
SP='/tmp/claude-1001/-home-fields-Fields-Orchestrator/d0cf8f8f-7d2e-434d-ad92-6e50edf06643/scratchpad'
OUT=SP+'/solar_tier3.html'
aerial='data:image/png;base64,'+base64.b64encode(open(SP+'/boundary.png','rb').read()).decode()
frames=json.load(open(SP+'/tier3_frames.json'))

TPL=r'''<style>
:root{--amber:#f2a900}
*{box-sizing:border-box}
.se{max-width:1000px;margin:0 auto;padding:22px 16px 40px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#eae4d6}
.se-wrap{background:#14140f;border-radius:20px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.se-head{padding:22px 24px 6px}
.se-ey{font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);font-weight:700;margin:0}
.se-h{font-size:clamp(1.4rem,4vw,2.05rem);font-weight:700;letter-spacing:-.02em;margin:.15em 0 .1em;color:#fff}
.se-sub{color:#a49f92;margin:0 0 6px;font-size:.95rem}
.se-stage{position:relative;width:100%;aspect-ratio:1280/880;background:#000}
.se-stage canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.se-narr{position:absolute;left:0;right:0;bottom:0;padding:52px 22px 18px;background:linear-gradient(transparent,rgba(0,0,0,.82));pointer-events:none}
.se-clock{font-variant-numeric:tabular-nums;font-size:.82rem;letter-spacing:.05em;color:#f4d58a;font-weight:600;margin:0 0 3px}
.se-line{font-size:clamp(1rem,2.6vw,1.35rem);line-height:1.35;margin:0;color:#fff;max-width:34ch;text-shadow:0 2px 12px rgba(0,0,0,.6)}
.se-flag{display:inline-block;margin-top:8px;padding:5px 11px;border-radius:100px;background:rgba(242,169,0,.16);border:1px solid rgba(242,169,0,.5);color:#ffdf9e;font-size:.78rem;font-weight:600;opacity:0;transition:.4s}
.se-flag.on{opacity:1}
.se-ctrl{padding:16px 22px 8px;background:#14140f;display:flex;flex-direction:column;gap:14px}
.se-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.se-seg{display:inline-flex;background:#242017;border-radius:100px;padding:3px}
.se-seg button{border:0;background:transparent;color:#b9b09a;font:inherit;font-weight:600;font-size:.9rem;padding:7px 18px;border-radius:100px;cursor:pointer;transition:.2s}
.se-seg button.on{background:var(--amber);color:#1c1c1a}
.se-play{border:0;background:#2e2a1f;color:#f4d58a;font:inherit;font-weight:700;font-size:.9rem;padding:9px 18px;border-radius:100px;cursor:pointer}
.se-play:hover{background:#3a3527}
.se-gold{border:1px solid rgba(242,169,0,.5);background:transparent;color:#f4d58a;font:inherit;font-weight:600;font-size:.86rem;padding:8px 15px;border-radius:100px;cursor:pointer}
.se-time{flex:1;min-width:180px;display:flex;align-items:center;gap:12px}
.se-time input[type=range]{flex:1;-webkit-appearance:none;appearance:none;height:5px;border-radius:5px;background:linear-gradient(90deg,#3a3527,#6b5a34,#f2a900,#6b5a34,#3a3527);outline:none}
.se-time input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:var(--amber);border:3px solid #14140f;cursor:pointer;box-shadow:0 0 10px rgba(242,169,0,.7)}
.se-t{font-variant-numeric:tabular-nums;color:#e9e0c8;font-weight:700;min-width:74px;text-align:right;font-size:.95rem}
.se-stats{display:flex;gap:10px;flex-wrap:wrap;padding:6px 22px 20px;background:#14140f}
.se-stat{flex:1;min-width:120px;background:#1f1c14;border-radius:12px;padding:11px 14px}
.se-stat .k{font-size:.64rem;letter-spacing:.06em;text-transform:uppercase;color:#8f866f}
.se-stat .v{font-size:1.15rem;font-weight:700;color:#f0e7cf}
.se-foot{padding:0 24px 22px;background:#14140f;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.68rem;color:#736c58;line-height:1.5}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div class="se"><div class="se-wrap">
 <div class="se-head">
  <p class="se-ey">Sun on this home &middot; full-scene shadows</p>
  <h1 class="se-h">Watch the light cross the block</h1>
  <p class="se-sub">17 Springvale Street, Robina &middot; house, neighbours &amp; trees &middot; faces the winter sun</p>
 </div>
 <div class="se-stage">
  <canvas id="cv" width="1280" height="880"></canvas>
  <div class="se-narr"><p class="se-clock" id="clock"></p><p class="se-line" id="line"></p>
   <span class="se-flag" id="flag">&#9728; North-facing living space in full sun</span></div>
 </div>
 <div class="se-ctrl">
  <div class="se-row">
   <div class="se-seg" id="seg"><button data-s="winter" class="on">&#10052; Winter</button><button data-s="summer">&#9728; Summer</button></div>
   <button class="se-play" id="play">&#9654;&nbsp;Play the day</button>
   <button class="se-gold" id="gold">Golden hour</button>
  </div>
  <div class="se-row"><div class="se-time"><input type="range" id="time" min="5" max="19" step="0.04" value="12"><span class="se-t" id="tlabel">12:00&nbsp;pm</span></div></div>
 </div>
 <div class="se-stats" id="stats"></div>
 <p class="se-foot">Sun computed from this address (lat &minus;28.075) &amp; date. Shadows of the house, the
  neighbouring homes AND the trees are ray-cast from free QLD LiDAR (classified point cloud, 2014) with our
  own code &mdash; no AI, no paid API. Block-level prototype, not a survey. Aerial &copy; Airbus / Vexcel.</p>
</div></div>
<script>
const AERIAL="__AERIAL__", FRAMES=__FRAMES__, LAT=-28.0747, DOY={winter:172,summer:355};
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
const img=new Image();img.src=AERIAL;
const FR={};for(const s of ['winter','summer']){FR[s]=FRAMES[s].map(f=>{const im=new Image();im.onload=draw;im.src=f.uri;return {h:f.h,el:f.el,az:f.az,img:im};});}
let season='winter',hour=12,playing=false,raf=null;
function sun(lat,doy,h){const r=Math.PI/180,L=lat*r;const d=(-23.44*r)*Math.cos((360/365*(doy+10))*r),H=15*(h-12)*r;
 let se=Math.sin(L)*Math.sin(d)+Math.cos(L)*Math.cos(d)*Math.cos(H);const el=Math.asin(Math.max(-1,Math.min(1,se)));
 let c=(Math.sin(d)-Math.sin(el)*Math.sin(L))/(Math.cos(el)*Math.cos(L)+1e-9);let az=Math.acos(Math.max(-1,Math.min(1,c)));if(H>0)az=2*Math.PI-az;return{az:az/r,el:el/r};}
function frameSpan(s){const a=FR[s];return [a[0].h,a[a.length-1].h];}
function bracket(s,h){const a=FR[s];if(h<=a[0].h)return{a:a[0],b:a[0],t:0};if(h>=a[a.length-1].h)return{a:a[a.length-1],b:a[a.length-1],t:0};
 for(let i=0;i<a.length-1;i++){if(h>=a[i].h&&h<=a[i+1].h)return{a:a[i],b:a[i+1],t:(h-a[i].h)/(a[i+1].h-a[i].h)};}return null;}
function hrlabel(h){if(Math.abs(h-12)<0.02)return'noon';let hh=Math.floor(h),mm=Math.round((h-hh)*60);if(mm===60){hh++;mm=0;}const ap=hh<12?'am':'pm';let x=hh%12;if(x===0)x=12;return x+':'+String(mm).padStart(2,'0')+' '+ap;}
const CMP=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];const cmp=a=>CMP[Math.round(a/22.5)%16];
function tint(h,el){if(el<=0)return[8,10,26,0.6];if(h<7)return[255,150,90,0.10*(7-h)];if(h>=16.5){const t=Math.min(1,(h-16.5)/2.5);return[255,150,55,0.06+0.30*t];}return[255,246,220,0.03];}
function proj(az,el){return [Math.max(46,Math.min(1234,640+(((az+180)%360)-180)/90*640)),92+(1-Math.min(1,el/90))*74];}
function draw(){
 const doy=DOY[season],s=sun(LAT,doy,hour),up=s.el>0.6;
 ctx.clearRect(0,0,1280,880);
 ctx.save();ctx.filter=up?'brightness('+(0.92+0.22*Math.min(1,s.el/45))+') saturate(1.04)':'brightness(0.5) saturate(0.7)';ctx.drawImage(img,0,0,1280,880);ctx.restore();
 if(up){const br=bracket(season,hour);if(br){if(br.t<1){ctx.save();ctx.globalAlpha=1-br.t;ctx.drawImage(br.a.img,0,0,1280,880);ctx.restore();}if(br.t>0){ctx.save();ctx.globalAlpha=br.t;ctx.drawImage(br.b.img,0,0,1280,880);ctx.restore();}}}
 const t=tint(hour,s.el);ctx.save();ctx.fillStyle='rgba('+t[0]+','+t[1]+','+t[2]+','+t[3]+')';ctx.fillRect(0,0,1280,880);ctx.restore();
 // sun arc + glyph
 const rs=frameSpan(season);ctx.save();ctx.beginPath();let f=true;
 for(let h=rs[0]-0.5;h<=rs[1]+0.5;h+=0.15){const q=sun(LAT,doy,h);if(q.el<=0)continue;const p=proj(q.az,q.el);if(f){ctx.moveTo(p[0],p[1]);f=false;}else ctx.lineTo(p[0],p[1]);}
 ctx.strokeStyle='rgba(255,214,130,0.4)';ctx.lineWidth=2.5;ctx.setLineDash([2,7]);ctx.lineCap='round';ctx.stroke();
 if(up){ctx.beginPath();f=true;for(let h=rs[0]-0.5;h<=hour;h+=0.12){const q=sun(LAT,doy,h);if(q.el<=0)continue;const p=proj(q.az,q.el);if(f){ctx.moveTo(p[0],p[1]);f=false;}else ctx.lineTo(p[0],p[1]);}ctx.setLineDash([]);ctx.strokeStyle='rgba(255,196,96,0.85)';ctx.lineWidth=3.5;ctx.shadowColor='rgba(255,180,80,.8)';ctx.shadowBlur=12;ctx.stroke();}
 ctx.restore();
 if(up){const p=proj(s.az,s.el);const g=ctx.createRadialGradient(p[0],p[1],2,p[0],p[1],58);g.addColorStop(0,'rgba(255,244,206,.98)');g.addColorStop(.38,'rgba(255,200,90,.55)');g.addColorStop(1,'rgba(255,200,90,0)');ctx.fillStyle=g;ctx.beginPath();ctx.arc(p[0],p[1],58,0,7);ctx.fill();ctx.fillStyle='#fff6df';ctx.beginPath();ctx.arc(p[0],p[1],9,0,7);ctx.fill();}
 ctx.save();ctx.translate(58,58);ctx.fillStyle='rgba(0,0,0,.6)';ctx.beginPath();ctx.arc(0,0,30,0,7);ctx.fill();ctx.fillStyle='#f2a900';ctx.beginPath();ctx.moveTo(0,-20);ctx.lineTo(7,10);ctx.lineTo(0,4);ctx.lineTo(-7,10);ctx.closePath();ctx.fill();ctx.fillStyle='#fff';ctx.font='700 14px sans-serif';ctx.textAlign='center';ctx.fillText('N',0,32);ctx.restore();
 text(s,doy,up);
}
function text(s,doy,up){
 document.getElementById('tlabel').textContent=hrlabel(hour);
 let clock,line,flag=false;
 if(!up){clock=season==='winter'?'Winter night':'Summer night';line='The sun is below the horizon.';}
 else{clock=(season==='winter'?'21 June (winter) · ':'21 December (summer) · ')+hrlabel(hour)+' · sun '+Math.round(s.el)+'° in the '+cmp(s.az);
  const maxel=season==='winter'?38:85;
  if(hour<8.5)line='Early '+(season==='winter'?'winter':'summer')+' sun, low from the '+cmp(s.az)+' — long shadows reach right across the yard from the house and the neighbours’ trees.';
  else if(s.el>maxel-3){if(season==='winter'){line='Winter midday. The sun sits '+Math.round(s.el)+'° high in the north and the north-facing living space is bathed in it.';flag=true;}else line='Summer midday. The sun is almost overhead ('+Math.round(s.el)+'°) — shadows all but vanish and the whole block is lit.';}
  else if(hour>15.5){if(season==='winter'){line='Winter afternoon. As the sun drops west, shadows stretch back across the block — golden light rakes the north face.';flag=(s.el>6);}else line='Long summer evening — the sun swings south-west and stays up past 7.';}
  else line=(season==='winter'?'Winter':'Summer')+' '+(hour<12?'morning':'afternoon')+'. Every shadow on the block — house, fences, trees — swings with the sun through the '+cmp(s.az)+'.';
 }
 document.getElementById('clock').textContent=clock;document.getElementById('line').textContent=line;document.getElementById('flag').classList.toggle('on',flag);
}
function stats(){const w=sun(LAT,DOY.winter,12),su=sun(LAT,DOY.summer,12);
 const items=[['Winter midday sun',Math.round(w.el)+'°'],['Summer midday sun',Math.round(su.el)+'°'],['Shadow source','LiDAR: house+trees'],['Faces','North']];
 document.getElementById('stats').innerHTML=items.map(i=>'<div class="se-stat"><div class="k">'+i[0]+'</div><div class="v">'+i[1]+'</div></div>').join('');}
document.getElementById('time').addEventListener('input',e=>{hour=parseFloat(e.target.value);stop();draw();});
document.getElementById('seg').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;[...e.currentTarget.children].forEach(x=>x.classList.remove('on'));b.classList.add('on');season=b.dataset.s;draw();});
document.getElementById('gold').addEventListener('click',()=>{stop();const doy=DOY[season];let best=17;for(let h=15;h<19;h+=0.05){if(sun(LAT,doy,h).el<8){best=h;break;}}hour=best;document.getElementById('time').value=hour;draw();});
const pb=document.getElementById('play');pb.addEventListener('click',()=>{if(playing)stop();else start();});
function start(){playing=true;pb.innerHTML='&#10073;&#10073;&nbsp;Pause';const sp=frameSpan(season);let t=performance.now(),h0=(hour>=sp[1]-0.1||hour<=sp[0])?sp[0]:hour;
 function step(now){if(!playing)return;const dt=(now-t)/1000;t=now;h0+=dt*(sp[1]-sp[0])/8;if(h0>=sp[1])h0=sp[0];hour=h0;document.getElementById('time').value=hour;draw();raf=requestAnimationFrame(step);}raf=requestAnimationFrame(step);}
function stop(){playing=false;if(raf)cancelAnimationFrame(raf);pb.innerHTML='&#9654;&nbsp;Play the day';}
img.onload=()=>{stats();draw();};if(img.complete)img.onload();
</script>'''
html=TPL.replace('__AERIAL__',aerial).replace('__FRAMES__',json.dumps(frames))
open(OUT,'w',encoding='utf-8').write(html)
print('WROTE',OUT,'len',len(html))
