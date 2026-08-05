import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U='https://fieldsestate.com.au/fridge';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const wait = ms => new Promise(r=>setTimeout(r,ms));

// A: left alone — must NOT open early, must nudge at 4s, give up at 12s
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
await p.goto(U,{waitUntil:'networkidle0'});
const s = () => p.evaluate(()=>{const f=document.getElementById('fridge');return{
  open:f.classList.contains('is-open'), nudging:f.classList.contains('is-nudging'),
  v:+parseFloat(getComputedStyle(f).getPropertyValue('--open')).toFixed(3),
  prompt:document.querySelector('.prompt').textContent.trim()};});
console.log('UNTOUCHED');
for (const t of [1000,2000,4400,5200,8000]) {
  await wait(t - (await p.evaluate(()=>Math.round(performance.now()))) + 0);
  console.log(`  ~${t}ms`, JSON.stringify(await s()));
}
await wait(5000);
console.log(`  ~13s  `, JSON.stringify(await s()), '  <- give-up open');
await p.close();

// B: tapped — opens on the tap, sound armed, prompt swaps
const q = await b.newPage();
await q.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
await q.goto(U,{waitUntil:'networkidle0'});
await wait(700);
console.log('\nTAPPED');
console.log('  before tap ', JSON.stringify(await q.evaluate(()=>({
  open:document.getElementById('fridge').classList.contains('is-open'),
  prompt:document.querySelector('.prompt').textContent.trim()}))));
await q.touchscreen.tap(195,400); await wait(2400);
console.log('  after tap  ', JSON.stringify(await q.evaluate(()=>({
  open:document.getElementById('fridge').classList.contains('is-open'),
  prompt:document.querySelector('.prompt').textContent.trim(),
  hum:window.fridgeAudio.state().humGain, humming:window.fridgeAudio.state().humming}))));
// hum must NOT move when the door moves
const py = await q.evaluate(()=>Math.round(document.querySelector('.prompt').getBoundingClientRect().top+8));
await q.touchscreen.tap(195,py); await wait(1800);
const h1 = await q.evaluate(()=>window.fridgeAudio.state().humGain);
await q.touchscreen.tap(195,400); await wait(2200);
const h2 = await q.evaluate(()=>window.fridgeAudio.state().humGain);
console.log(`  hum shut ${h1} -> open ${h2}  ${h1===h2 ? 'CONSTANT ✓' : 'STILL DUCKING ✗'}`);
console.log('  reopened  ', JSON.stringify(await q.evaluate(()=>({
  open:document.getElementById('fridge').classList.contains('is-open')}))));
await b.close();
