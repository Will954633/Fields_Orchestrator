import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U='https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/index.html?debug=1';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required']});
const p = await b.newPage(); await p.setViewport({width:390,height:844,deviceScaleFactor:2});
const errs=[],net=[]; p.on('pageerror',e=>errs.push(String(e)));
p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
p.on('response',r=>{ if(/\.m4a/.test(r.url())) net.push(`${r.status()} ${r.url().split('/').pop()}`); });
await p.goto(U,{waitUntil:'networkidle0'});
const wait = ms => new Promise(r=>setTimeout(r,ms));
await wait(1200);

console.log('audio files fetched:', net.length?net:'NONE');
console.log('after load        :', JSON.stringify(await p.evaluate(()=>window.fridgeAudio.state())));

// a real click = user activation
await p.mouse.click(195, 790);
await wait(900);
console.log('after tap (close) :', JSON.stringify(await p.evaluate(()=>window.fridgeAudio.state())));
console.log('mute btn visible  :', await p.evaluate(()=>document.getElementById('muteBtn').classList.contains('on')));

await wait(1400);
await p.mouse.click(195, 790);   // reopen
await wait(1400);
const st = await p.evaluate(()=>({a:window.fridgeAudio.state(),
  open:document.getElementById('fridge').classList.contains('is-open')}));
console.log('after reopen      :', JSON.stringify(st));

// mute
await p.click('#muteBtn'); await wait(500);
console.log('after mute        :', JSON.stringify(await p.evaluate(()=>window.fridgeAudio.state())));
await p.click('#muteBtn'); await wait(500);
console.log('after unmute      :', JSON.stringify(await p.evaluate(()=>window.fridgeAudio.state())));
console.log('errors:', errs.length?errs:'none');
await b.close();
