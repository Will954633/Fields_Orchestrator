#!/usr/bin/env python3
"""Build the interactive Solar Arc experience as a self-contained artifact HTML."""
import base64, json
SP='/tmp/claude-1001/-home-fields-Fields-Orchestrator/d0cf8f8f-7d2e-434d-ad92-6e50edf06643/scratchpad'
OUT=SP+'/solar_experience.html'
aerial='data:image/png;base64,'+base64.b64encode(open(SP+'/boundary.png','rb').read()).decode()

# footprints EXTRACTED from the aerial by our own classic CV (colour segmentation +
# contour), clipped to the cadastral polygon. No AI. Largest = house, rest = outbuilding.
BUILDINGS=json.load(open(SP+'/lidar_all_buildings.json'))  # subject + neighbour buildings, true heights (LiDAR)

TPL=r'''<style>
:root{--paper:#efe9dd;--green:#24392c;--terra:#c1632f;--amber:#f2a900;--ink:#1c1c1a}
*{box-sizing:border-box}
.se{max-width:1000px;margin:0 auto;padding:22px 16px 40px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#eae4d6}
.se-wrap{background:#14140f;border-radius:20px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.se-head{padding:22px 24px 6px}
.se-ey{font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);font-weight:700;margin:0}
.se-h{font-size:clamp(1.4rem,4vw,2.05rem);font-weight:700;letter-spacing:-.02em;margin:.15em 0 .1em;color:#fff;text-wrap:balance}
.se-sub{color:#a49f92;margin:0 0 6px;font-size:.95rem}
.se-stage{position:relative;width:100%;aspect-ratio:1280/880;background:#000}
.se-stage canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.se-narr{position:absolute;left:0;right:0;bottom:0;padding:52px 22px 18px;background:linear-gradient(transparent,rgba(0,0,0,.82));pointer-events:none}
.se-clock{font-variant-numeric:tabular-nums;font-size:.82rem;letter-spacing:.05em;color:#f4d58a;font-weight:600;margin:0 0 3px}
.se-line{font-size:clamp(1rem,2.6vw,1.35rem);line-height:1.35;margin:0;color:#fff;text-wrap:balance;max-width:34ch;text-shadow:0 2px 12px rgba(0,0,0,.6)}
.se-flag{display:inline-block;margin-top:8px;padding:5px 11px;border-radius:100px;background:rgba(242,169,0,.16);border:1px solid rgba(242,169,0,.5);color:#ffdf9e;font-size:.78rem;font-weight:600;opacity:0;transform:translateY(4px);transition:.4s}
.se-flag.on{opacity:1;transform:none}
.se-ctrl{padding:16px 22px 8px;background:#14140f;display:flex;flex-direction:column;gap:14px}
.se-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.se-seg{display:inline-flex;background:#242017;border-radius:100px;padding:3px}
.se-seg button{border:0;background:transparent;color:#b9b09a;font:inherit;font-weight:600;font-size:.9rem;padding:7px 18px;border-radius:100px;cursor:pointer;transition:.2s}
.se-seg button.on{background:var(--amber);color:#1c1c1a}
.se-play{border:0;background:#2e2a1f;color:#f4d58a;font:inherit;font-weight:700;font-size:.9rem;padding:9px 18px;border-radius:100px;cursor:pointer;display:inline-flex;align-items:center;gap:8px}
.se-play:hover{background:#3a3527}
.se-gold{border:1px solid rgba(242,169,0,.5);background:transparent;color:#f4d58a;font:inherit;font-weight:600;font-size:.86rem;padding:8px 15px;border-radius:100px;cursor:pointer}
.se-gold:hover{background:rgba(242,169,0,.12)}
.se-time{flex:1;min-width:180px;display:flex;align-items:center;gap:12px}
.se-time input[type=range]{flex:1;-webkit-appearance:none;appearance:none;height:5px;border-radius:5px;background:linear-gradient(90deg,#3a3527,#6b5a34,#f2a900,#6b5a34,#3a3527);outline:none}
.se-time input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:20px;height:20px;border-radius:50%;background:var(--amber);border:3px solid #14140f;cursor:pointer;box-shadow:0 0 10px rgba(242,169,0,.7)}
.se-time input[type=range]::-moz-range-thumb{width:20px;height:20px;border-radius:50%;background:var(--amber);border:3px solid #14140f;cursor:pointer}
.se-t{font-variant-numeric:tabular-nums;color:#e9e0c8;font-weight:700;min-width:74px;text-align:right;font-size:.95rem}
.se-stats{display:flex;gap:10px;flex-wrap:wrap;padding:6px 22px 20px;background:#14140f}
.se-stat{flex:1;min-width:120px;background:#1f1c14;border-radius:12px;padding:11px 14px}
.se-stat .k{font-size:.64rem;letter-spacing:.06em;text-transform:uppercase;color:#8f866f}
.se-stat .v{font-size:1.15rem;font-weight:700;color:#f0e7cf;font-variant-numeric:tabular-nums}
.se-foot{padding:0 24px 22px;background:#14140f;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.68rem;color:#736c58;line-height:1.5}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div class="se">
 <div class="se-wrap">
  <div class="se-head">
   <p class="se-ey">Sun on this home</p>
   <h1 class="se-h">Watch the light cross the block</h1>
   <p class="se-sub">17 Springvale Street, Robina &middot; lot 828&nbsp;m&sup2; &middot; faces the winter sun</p>
  </div>
  <div class="se-stage">
   <canvas id="cv" width="1280" height="880"></canvas>
   <div class="se-narr">
     <p class="se-clock" id="clock"></p>
     <p class="se-line" id="line"></p>
     <span class="se-flag" id="flag">&#9728; North-facing living space in full sun</span>
   </div>
  </div>
  <div class="se-ctrl">
   <div class="se-row">
    <div class="se-seg" id="seg">
      <button data-s="winter" class="on">&#10052; Winter</button>
      <button data-s="summer">&#9728; Summer</button>
    </div>
    <button class="se-play" id="play">&#9654;&nbsp;Play the day</button>
    <button class="se-gold" id="gold">Golden hour</button>
   </div>
   <div class="se-row">
    <div class="se-time">
      <input type="range" id="time" min="4.5" max="19.5" step="0.05" value="12">
      <span class="se-t" id="tlabel">12:00&nbsp;pm</span>
    </div>
   </div>
  </div>
  <div class="se-stats" id="stats"></div>
  <p class="se-foot">Sun computed from this address (lat &minus;28.075) &amp; date. House &amp; neighbouring buildings, true heights, from free QLD LiDAR (classified point cloud, 2014), georeferenced by our own code (no AI) &mdash; a working prototype: block-level, not a survey.
   Aerial &copy; Airbus / Vexcel.</p>
 </div>
</div>
<script>
const BUILDINGS=__BUILDINGS__, MPP=0.066;
const LAT=-28.0747, DOY={winter:172,summer:355};
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const img=new Image(); img.src="__AERIAL__";
let season='winter', hour=12, playing=false, raf=null;

function sun(lat,doy,h){const r=Math.PI/180,L=lat*r;
 const d=(-23.44*r)*Math.cos((360/365*(doy+10))*r), H=15*(h-12)*r;
 let sel=Math.sin(L)*Math.sin(d)+Math.cos(L)*Math.cos(d)*Math.cos(H);
 const el=Math.asin(Math.max(-1,Math.min(1,sel)));
 let c=(Math.sin(d)-Math.sin(el)*Math.sin(L))/(Math.cos(el)*Math.cos(L)+1e-9);
 let az=Math.acos(Math.max(-1,Math.min(1,c))); if(H>0) az=2*Math.PI-az;
 return {az:az/r, el:el/r};}
function riseSet(doy){let lo=null,hi=null;for(let h=3;h<=21;h+=0.02){if(sun(LAT,doy,h).el>0){if(lo===null)lo=h;hi=h;}}return[lo,hi];}
function hull(P){P=P.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);const cr=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
 let L=[];for(const p of P){while(L.length>=2&&cr(L[L.length-2],L[L.length-1],p)<=0)L.pop();L.push(p);}
 let U=[];for(let i=P.length-1;i>=0;i--){const p=P[i];while(U.length>=2&&cr(U[U.length-2],U[U.length-1],p)<=0)U.pop();U.push(p);}
 L.pop();U.pop();return L.concat(U);}
function poly(p){ctx.beginPath();ctx.moveTo(p[0][0],p[0][1]);for(let i=1;i<p.length;i++)ctx.lineTo(p[i][0],p[i][1]);ctx.closePath();}

// sky tint by hour/elevation
function tint(h,el){
 // returns [r,g,b,a] overlay
 if(el<=0) return [8,10,26,0.62];              // night
 if(h<7.2) return [255,150,90,0.30*(7.2-h)/2]; // dawn warm
 if(h>=16.2){const t=Math.min(1,(h-16.2)/3);return [255,160,60,0.10+0.42*t];} // golden->dusk
 return [255,244,214,0.05];                    // midday neutral-warm
}
const COMPASS=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
const cmp=a=>COMPASS[Math.round(a/22.5)%16];

function draw(){
 const doy=DOY[season], s=sun(LAT,doy,hour), up=s.el>0;
 ctx.clearRect(0,0,1280,880);
 ctx.save(); if(up){ctx.filter='brightness('+(0.9+0.25*Math.min(1,s.el/45))+') saturate(1.05)';}else{ctx.filter='brightness(0.5) saturate(0.7)';}
 ctx.drawImage(img,0,0,1280,880); ctx.restore();
 // shadows
 if(up){
  const off=(Math.max(...BUILDINGS.map(b=>b.h))); // just for alpha calc
  const a=Math.min(0.5,0.22+0.5*(1-Math.min(1,s.el/55)));
  const sh=document.createElement('canvas');sh.width=1280;sh.height=880;const sx=sh.getContext('2d');
  sx.fillStyle='#0a0c16';
  for(const b of BUILDINGS){
   const d=(b.h/Math.tan(s.el*Math.PI/180))/MPP;
   const vx=-Math.sin(s.az*Math.PI/180)*d, vy=Math.cos(s.az*Math.PI/180)*d;
   const base=b.pts, top=b.pts.map(p=>[p[0]+vx,p[1]+vy]);
   const put=pp=>{sx.beginPath();sx.moveTo(pp[0][0],pp[0][1]);for(let i=1;i<pp.length;i++)sx.lineTo(pp[i][0],pp[i][1]);sx.closePath();sx.fill();};
   put(base);put(top);
   for(let i=0;i<base.length;i++){const j=(i+1)%base.length;put([base[i],base[j],top[j],top[i]]);}
  }
  ctx.save();ctx.globalAlpha=a;ctx.filter='blur(2.5px)';ctx.drawImage(sh,0,0);ctx.restore();
  // redraw roofs on top so house sits above its shadow
  for(const b of BUILDINGS){ctx.save();poly(b.pts);ctx.clip();ctx.filter='brightness(1.02)';ctx.drawImage(img,0,0,1280,880);ctx.restore();}
 }
 // sky tint
 const t=tint(hour,s.el);ctx.save();ctx.fillStyle='rgba('+t[0]+','+t[1]+','+t[2]+','+t[3]+')';ctx.fillRect(0,0,1280,880);ctx.restore();
 // the sun's ARC across the sky (the day's whole path) + the sun on it
 const proj=(az,el)=>[Math.max(46,Math.min(1234,640+(((az+180)%360)-180)/90*640)), 92+(1-Math.min(1,el/90))*74];
 {const doyA=DOY[season], rs=riseSet(doyA); ctx.save();
  // faint full-day arc
  ctx.beginPath(); let f=true;
  for(let h=rs[0];h<=rs[1];h+=0.12){const q=sun(LAT,doyA,h);const p=proj(q.az,q.el);if(f){ctx.moveTo(p[0],p[1]);f=false;}else ctx.lineTo(p[0],p[1]);}
  ctx.strokeStyle='rgba(255,214,130,0.42)';ctx.lineWidth=2.5;ctx.setLineDash([2,7]);ctx.lineCap='round';ctx.stroke();
  // solid trail from sunrise up to NOW
  if(up){ctx.beginPath();f=true;for(let h=rs[0];h<=hour;h+=0.12){const q=sun(LAT,doyA,h);const p=proj(q.az,q.el);if(f){ctx.moveTo(p[0],p[1]);f=false;}else ctx.lineTo(p[0],p[1]);}
   ctx.setLineDash([]);ctx.strokeStyle='rgba(255,196,96,0.85)';ctx.lineWidth=3.5;ctx.shadowColor='rgba(255,180,80,.8)';ctx.shadowBlur=12;ctx.stroke();}
  ctx.restore();}
 // sun glyph on the arc when up
 if(up){
  const p=proj(s.az,s.el), gx=p[0], sy=p[1];
  const g=ctx.createRadialGradient(gx,sy,2,gx,sy,58);
  g.addColorStop(0,'rgba(255,244,206,0.98)');g.addColorStop(0.38,'rgba(255,200,90,0.55)');g.addColorStop(1,'rgba(255,200,90,0)');
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(gx,sy,58,0,7);ctx.fill();
  ctx.fillStyle='#fff6df';ctx.beginPath();ctx.arc(gx,sy,9,0,7);ctx.fill();
 }
 // compass
 ctx.save();ctx.translate(66,70);ctx.fillStyle='rgba(0,0,0,.5)';ctx.beginPath();ctx.arc(0,0,30,0,7);ctx.fill();
 ctx.fillStyle='#f2a900';ctx.beginPath();ctx.moveTo(0,-20);ctx.lineTo(7,10);ctx.lineTo(0,4);ctx.lineTo(-7,10);ctx.closePath();ctx.fill();
 ctx.fillStyle='#fff';ctx.font='700 14px sans-serif';ctx.textAlign='center';ctx.fillText('N',0,32);ctx.restore();
 updateText(s,doy,up);
}

function fmt(h){let hh=Math.floor(h),mm=Math.round((h-hh)*60);if(mm===60){hh++;mm=0;}const ap=hh<12?'am':'pm';let h12=hh%12;if(h12===0)h12=12;return h12+':'+String(mm).padStart(2,'0')+' '+ap;}
function updateText(s,doy,up){
 document.getElementById('tlabel').textContent=fmt(hour);
 const noon=[]; for(let h=4;h<=20;h+=0.1){const e=sun(LAT,doy,h).el; noon.push(e);}
 const maxel=Math.max(...noon);
 let clock, line, flagOn=false;
 if(!up){clock=(season==='winter'?'Winter night':'Summer night');line='The sun is below the horizon. In '+(season==='winter'?'winter':'summer')+' the days are '+(season==='winter'?'short \u2014 first light comes late':'long \u2014 light lingers past 7pm')+'.';}
 else{
  clock=(season==='winter'?'21 June (winter) \u00B7 ':'21 December (summer) \u00B7 ')+fmt(hour)+' \u00B7 sun '+Math.round(s.el)+'\u00B0 in the '+cmp(s.az);
  if(hour<8) line='Early '+ (season==='winter'?'winter':'summer') +' sun comes in low from the '+cmp(s.az)+', throwing long shadows across the yard.';
  else if(s.el>maxel-3){
    if(season==='winter'){line='Winter midday. The sun sits only '+Math.round(s.el)+'\u00B0 high in the north \u2014 and the north-facing living space is bathed in it.';flagOn=true;}
    else{line='Summer midday. The sun is almost overhead ('+Math.round(s.el)+'\u00B0), so shadows all but vanish and the whole block is lit.';}
  }
  else if(hour>16){
    if(season==='winter'){line='Winter afternoon. As the sun drops to the west, the shadow stretches back across the block \u2014 golden light rakes the north face.';flagOn=(s.el>6);}
    else line='Long summer evening. The sun swings to the south-west and stays up past 7 \u2014 hours of low, warm light.';
  }
  else line=(season==='winter'?'Winter':'Summer')+' '+(hour<12?'morning':'afternoon')+'. The sun tracks through the '+cmp(s.az)+' at '+Math.round(s.el)+'\u00B0, and the shadow swings with it.';
 }
 document.getElementById('clock').textContent=clock;
 document.getElementById('line').textContent=line;
 document.getElementById('flag').classList.toggle('on',flagOn);
}

function stats(){
 const w=sun(LAT,DOY.winter,12), s=sun(LAT,DOY.summer,12);
 const [wr,ws]=riseSet(DOY.winter);
 const items=[['Winter midday sun',Math.round(w.el)+'\u00B0'],['Summer midday sun',Math.round(s.el)+'\u00B0'],['Winter daylight',(Math.round((ws-wr)*10)/10)+' hrs'],['Faces','North']];
 document.getElementById('stats').innerHTML=items.map(i=>'<div class="se-stat"><div class="k">'+i[0]+'</div><div class="v">'+i[1]+'</div></div>').join('');
}

// controls
document.getElementById('time').addEventListener('input',e=>{hour=parseFloat(e.target.value);stop();draw();});
document.getElementById('seg').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
 [...e.currentTarget.children].forEach(x=>x.classList.remove('on'));b.classList.add('on');season=b.dataset.s;draw();});
document.getElementById('gold').addEventListener('click',()=>{stop();const doy=DOY[season];
 // find evening golden hour (~sun el 6deg descending)
 let best=17;for(let h=15;h<20;h+=0.05){if(sun(LAT,doy,h).el<8){best=h;break;}}
 hour=best;document.getElementById('time').value=hour;draw();});
const playBtn=document.getElementById('play');
playBtn.addEventListener('click',()=>{if(playing)stop();else start();});
function start(){playing=true;playBtn.innerHTML='&#10073;&#10073;&nbsp;Pause';const doy=DOY[season];const [r,st]=riseSet(doy);
 let t=performance.now(),h0=(hour>=st-0.2||hour<=r)?r:hour;
 function step(now){if(!playing)return;const dt=(now-t)/1000;t=now;h0+=dt*(st-r)/7;if(h0>=st){h0=r;}
  hour=h0;document.getElementById('time').value=hour;draw();raf=requestAnimationFrame(step);}
 raf=requestAnimationFrame(step);}
function stop(){playing=false;if(raf)cancelAnimationFrame(raf);playBtn.innerHTML='&#9654;&nbsp;Play the day';}

img.onload=()=>{stats();draw();};
if(img.complete)img.onload();
</script>'''

html=TPL.replace('__BUILDINGS__',json.dumps(BUILDINGS)).replace('__AERIAL__',aerial)
open(OUT,'w').write(html)
print('WROTE',OUT,'len',len(html))
