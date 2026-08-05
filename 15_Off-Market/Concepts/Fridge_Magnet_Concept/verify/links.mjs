import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const BASE='https://fieldsestate.com.au/fridge';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const wait=ms=>new Promise(r=>setTimeout(r,ms));

// what are the four links?
const p0 = await b.newPage(); await p0.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
await p0.goto(BASE,{waitUntil:'domcontentloaded'}); await wait(2000);
const n = await p0.evaluate(()=>document.querySelectorAll('.shelf a').length);
await p0.close();
console.log(`found ${n} option links\n`);

for (let i=0;i<n;i++) {
  const p = await b.newPage();
  await p.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
  const bad=[]; p.on('pageerror',e=>bad.push('JS: '+e));
  await p.goto(BASE,{waitUntil:'domcontentloaded'}); await wait(2000);
  await p.touchscreen.tap(195,400);            // open the door
  await wait(2600);
  const info = await p.evaluate((i)=>{
    const a=[...document.querySelectorAll('.shelf a')][i];
    const r=a.getBoundingClientRect();
    return {label:a.querySelector('.label').childNodes[0].nodeValue.trim(),
            href:a.getAttribute('href'),
            c:[Math.round(r.x+r.width/2),Math.round(r.y+r.height/2)]};
  }, i);
  await p.touchscreen.tap(info.c[0],info.c[1]);
  await p.waitForNavigation({timeout:15000}).catch(()=>{});
  await wait(2500);
  const landed = await p.evaluate(()=>({title:document.title, h1:(document.querySelector('h1')||{}).textContent||'', body:document.body.innerText.length}));
  const notFound = /not found|404/i.test(landed.title) || /not found/i.test(landed.h1);
  console.log(`${i+1}. ${info.label}`);
  console.log(`   href    ${info.href.replace('https://fieldsestate.com.au','')}`);
  console.log(`   landed  ${p.url().replace('https://fieldsestate.com.au','')}`);
  console.log(`   title   ${landed.title.slice(0,58)}`);
  console.log(`   ${notFound ? 'BROKEN — 404 page' : (landed.body>400 ? 'OK — real content ('+landed.body+' chars)' : 'THIN — only '+landed.body+' chars')}${bad.length?'  ERRORS: '+bad.join(';'):''}\n`);
  await p.close();
}

// the secret door
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
await p.goto(BASE,{waitUntil:'domcontentloaded'}); await wait(2000);
await p.touchscreen.tap(195,400); await wait(2600);
const c = await p.evaluate(()=>{const r=document.getElementById('secret').getBoundingClientRect();
  return [Math.round(r.x+r.width/2),Math.round(r.y+r.height/2)];});
await p.touchscreen.tap(c[0],c[1]);
await p.waitForNavigation({timeout:12000}).catch(()=>{});
await wait(2000);
console.log('5. secret button');
console.log('   landed  '+p.url().replace('https://fieldsestate.com.au','')+'  |  '+(await p.title()).slice(0,50));
await b.close();
