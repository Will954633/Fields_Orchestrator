import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const U = process.env.U || 'https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/index.html';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2,isMobile:true,hasTouch:true});
const errs=[]; p.on('pageerror',e=>errs.push(String(e)));
p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
p.on('response',r=>{if(r.status()>=400)errs.push(r.status()+' '+r.url())});
await p.goto(U,{waitUntil:'domcontentloaded'});
await new Promise(r=>setTimeout(r,2500));  // analytics keeps the network busy on prod; networkidle0 never settles
const wait=ms=>new Promise(r=>setTimeout(r,ms));
await wait(500);
await p.screenshot({path:'verify/v_shut.png'});
console.log('badge box:', JSON.stringify(await p.evaluate(()=>{const b=document.querySelector('.badge').getBoundingClientRect();
  return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};})));

// open the door
await p.touchscreen.tap(195,400); await wait(2400);
await p.screenshot({path:'verify/v_open.png'});
const s = await p.evaluate(()=>{
  const sec=document.getElementById('secret'), r=sec.getBoundingClientRect();
  const el=document.elementFromPoint(Math.round(r.x+r.width/2), Math.round(r.y+r.height/2));
  return {secret:{x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width)},
          visible:r.width>0 && r.x>=0 && r.x<390,
          hit: el ? el.tagName+'.'+String(el.className) : 'NULL',
          hittable: !!(el&&el.closest&&el.closest('.secret'))};
});
console.log('secret button:', JSON.stringify(s));

// press it
let navUrl=null; p.on('framenavigated',f=>{ if(f===p.mainFrame()) navUrl=f.url(); });
await p.click('#secret').catch(e=>console.log('click failed:',e.message));
await wait(700);  await p.screenshot({path:'verify/v_vault_mid.png'});
console.log('mid-drop:', JSON.stringify(await p.evaluate(()=>({
  vault:document.getElementById('fridge').classList.contains('is-vault'),
  panel:getComputedStyle(document.querySelector('.innerPanel')).transform.slice(0,42)}))));
await wait(700);  await p.screenshot({path:'verify/v_vault.png'});
await wait(1400);
console.log('navigated to:', navUrl);
console.log('errors:', errs.length?errs:'none');
await b.close();
