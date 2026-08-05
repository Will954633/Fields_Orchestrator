import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U='https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/index.html?debug=1';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage(); await p.setViewport({width:390,height:844,deviceScaleFactor:2});
const errs=[]; p.on('pageerror',e=>errs.push(String(e))); p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
await p.goto(U,{waitUntil:'networkidle0'});

const snap = () => p.evaluate(()=>{
  const f=document.getElementById('fridge'), cs=getComputedStyle(f);
  if(!f) return {gone:true};
  return { open:f.classList.contains('is-open'), closing:f.classList.contains('is-closing'),
    openVar:parseFloat(cs.getPropertyValue('--open')),
    flick:+getComputedStyle(document.querySelector('.flick')).opacity,
    shelves:[...document.querySelectorAll('.shelf')].map(s=>+(+getComputedStyle(s).opacity).toFixed(2)),
    aria:document.getElementById('srToggle').getAttribute('aria-expanded') };
});
const wait = ms => new Promise(r=>setTimeout(r,ms));

// the door no longer auto-opens — the first open must be a tap, so that it has sound
await wait(300);  console.log('t=0.3s shut     ', JSON.stringify(await snap()));
await p.mouse.click(195, 400);
await wait(700);  console.log('t+0.7s opening ', JSON.stringify(await snap()));
await p.screenshot({path:'verify/t_flicker.png'});
await wait(1800); console.log('t+2.5s open    ', JSON.stringify(await snap()));
await p.screenshot({path:'verify/t_open.png'});

// tap the PROMPT / room below the fridge -> should close
const py = await p.evaluate(()=>{const r=document.querySelector('.prompt').getBoundingClientRect();return Math.round(r.top+r.height/2)});
await p.mouse.click(195, py);
await wait(120);  console.log('after tap door ', JSON.stringify(await snap()));
await wait(1200); console.log('t+1.3s closed  ', JSON.stringify(await snap()));
await p.screenshot({path:'verify/t_reclosed.png'});

// tap again -> reopen
await p.mouse.click(195, py);
await wait(2000); console.log('after re-tap   ', JSON.stringify(await snap()));

// tap INSIDE the cavity between shelves (not a link) -> must NOT close
const before = (await snap()).open;
const gapY = await p.evaluate(()=>{const s=[...document.querySelectorAll('.shelf')];
  const a=s[0].getBoundingClientRect(), b=s[1].getBoundingClientRect();
  return Math.round((a.bottom+b.top)/2);});
await p.mouse.click(195, gapY);
await wait(300);
const after = (await snap()).open;
console.log('cavity tap kept it open:', before===true && after===true, '(y='+gapY+')');
console.log('errors:', errs.length?errs:'none');
await b.close();
