import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U='https://fieldsestate.com.au/fridge';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2, isMobile:true, hasTouch:true});
await p.goto(U,{waitUntil:'networkidle0'});
// count EVERY event a real tap delivers to document
await p.evaluate(()=>{
  window.__ev=[];
  ['pointerdown','pointerup','touchstart','touchend','mousedown','mouseup','click'].forEach(t=>
    document.addEventListener(t, e=>window.__ev.push(t+'@'+Math.round(performance.now())), true));
  window.__toggles=[];
  const f=document.getElementById('fridge');
  new MutationObserver(()=>window.__toggles.push(
     (f.classList.contains('is-open')?'OPEN':'shut')+'@'+Math.round(performance.now())))
     .observe(f,{attributes:true,attributeFilter:['class']});
});
const wait = ms => new Promise(r=>setTimeout(r,ms));
const st = () => p.evaluate(()=>({open:document.getElementById('fridge').classList.contains('is-open'),
  v:+parseFloat(getComputedStyle(document.getElementById('fridge')).getPropertyValue('--open')).toFixed(2)}));
const probe = (x,y)=>p.evaluate((x,y)=>{const e=document.elementFromPoint(x,y);
  return e?(e.tagName+'.'+String(e.className).split(' ').join('.')):'NULL';},x,y);

await wait(500);
console.log('SHUT           ', JSON.stringify(await st()), '| under finger:', await probe(195,400));

console.log('\n--- ONE tap on the door ---');
await p.evaluate(()=>{window.__ev=[];window.__toggles=[]});
await p.touchscreen.tap(195,400); await wait(2400);
console.log('  events:', (await p.evaluate(()=>window.__ev)).join(' '));
console.log('  class changes:', (await p.evaluate(()=>window.__toggles)).join(' '));
console.log('  state:', JSON.stringify(await st()));

console.log('\n--- ONE tap on the room (close) ---');
await p.evaluate(()=>{window.__ev=[];window.__toggles=[]});
const py = await p.evaluate(()=>Math.round(document.querySelector('.prompt').getBoundingClientRect().top+8));
await p.touchscreen.tap(195,py); await wait(1600);
console.log('  class changes:', (await p.evaluate(()=>window.__toggles)).join(' '));
console.log('  state:', JSON.stringify(await st()), '| under finger(195,400):', await probe(195,400));

console.log('\n--- ONE tap to REOPEN ---');
await p.evaluate(()=>{window.__ev=[];window.__toggles=[]});
await p.touchscreen.tap(195,400); await wait(2400);
console.log('  events:', (await p.evaluate(()=>window.__ev)).join(' '));
console.log('  class changes:', (await p.evaluate(()=>window.__toggles)).join(' '));
console.log('  state:', JSON.stringify(await st()));
await b.close();
