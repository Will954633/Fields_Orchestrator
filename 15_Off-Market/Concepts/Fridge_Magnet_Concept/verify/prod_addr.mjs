import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2});
await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1');
const errs=[]; p.on('pageerror',e=>errs.push(String(e))); p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
await p.goto('https://fieldsestate.com.au/fridge',{waitUntil:'domcontentloaded'});
await new Promise(r=>setTimeout(r,1500));
let navTo=null;
await p.setRequestInterception(true);
p.on('request',r=>{const u=r.url();
  if(/fieldsestate\.com\.au\/off-market\//.test(u)&&r.isNavigationRequest()&&r.frame()===p.mainFrame()){navTo=u;r.respond({status:200,contentType:'text/html',body:'stub'});}
  else r.continue();});
await p.evaluate(()=>document.getElementById('srToggle').click());
await new Promise(r=>setTimeout(r,700));
await p.evaluate(()=>{[...document.querySelectorAll('.shelf a')].find(x=>x.dataset.anchor==='#v5-valuation').click();});
await new Promise(r=>setTimeout(r,300));
console.log('sheet open=',await p.$eval('#addrSheet',e=>!e.hidden&&e.classList.contains('is-open')),' hint=',JSON.stringify(await p.$eval('#addrHint',e=>e.textContent)));
await p.type('#addrInput','cheltenham drive robina',{delay:25});
await new Promise(r=>setTimeout(r,3500));
const sugg=await p.$$eval('.addrOpt',bs=>bs.map(b=>b.textContent));
console.log('suggestions=',sugg.length, sugg[0]||'');
await p.screenshot({path:'verify/prod_flow_sheet.png'});
if(sugg.length){await p.evaluate(()=>document.querySelector('.addrOpt').click());await new Promise(r=>setTimeout(r,400));}
console.log('address pick (worth) -> nav=',navTo);
console.log('console errors:',errs.length?errs:'none');
await b.close();
