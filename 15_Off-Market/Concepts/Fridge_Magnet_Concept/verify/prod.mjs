import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U = 'https://fieldsestate.com.au/fridge';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2});
await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1');
const errs=[], bad=[];
p.on('pageerror',e=>errs.push(String(e)));
p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
p.on('response',r=>{ if(r.status()>=400) bad.push(`${r.status()} ${r.url()}`); });

// SSR contract: the four links must be in the HTML before any JS runs
const raw = await (await fetch(U)).text();
const inHtml = (raw.match(/class="shelf a"|<a href="https:\/\/fieldsestate\.com\.au\//g)||[]).length;
console.log('links present in raw HTML (no JS):', (raw.match(/fieldsestate\.com\.au\/(market-intelligence|sold|for-sale|analyse-your-home)/g)||[]).length, '/ 4');
console.log('raw HTML bytes:', raw.length, '| has <base>:', /<base href="\/fridge\/">/.test(raw), '| noindex:', /noindex/.test(raw));

const t=Date.now();
await p.goto(U,{waitUntil:'networkidle0'});
console.log('load ms:', Date.now()-t);
await new Promise(r=>setTimeout(r,3200));

const st = await p.evaluate(()=>({
  open: document.getElementById('fridge').classList.contains('is-open'),
  openVar: parseFloat(getComputedStyle(document.getElementById('fridge')).getPropertyValue('--open')),
  shelves: [...document.querySelectorAll('.shelf')].map(s=>+(+getComputedStyle(s).opacity).toFixed(2)),
  links: [...document.querySelectorAll('.shelf a')].map(a=>a.href),
  linksHittable: [...document.querySelectorAll('.shelf a')].every(a=>{
    const r=a.getBoundingClientRect(); const el=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
    return !!(el && el.closest && el.closest('.shelf a'));
  }),
  audio: window.fridgeAudio ? window.fridgeAudio.state() : null,
  posthog: typeof window.posthog === 'object' && typeof window.posthog.capture === 'function',
  overflowX: document.documentElement.scrollWidth > window.innerWidth,
}));
console.log(JSON.stringify(st,null,1));
await p.screenshot({path:'verify/prod_open.png'});
// tap to close
const py = await p.evaluate(()=>{const r=document.querySelector('.prompt').getBoundingClientRect();return Math.round(r.top+r.height/2)});
await p.mouse.click(195, py); await new Promise(r=>setTimeout(r,1400));
console.log('after close tap:', JSON.stringify(await p.evaluate(()=>({
  open:document.getElementById('fridge').classList.contains('is-open'),
  openVar:parseFloat(getComputedStyle(document.getElementById('fridge')).getPropertyValue('--open')),
  hum: window.fridgeAudio.state().humGain }))));
await p.screenshot({path:'verify/prod_closed.png'});
console.log('4xx/5xx:', bad.length?bad:'none');
console.log('console errors:', errs.length?errs:'none');
await b.close();
