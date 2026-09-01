import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
for (const anchor of ['#v5-near','#v5-new','#v5-valuation']) {
  const p = await b.newPage();
  await p.setViewport({width:390,height:844,deviceScaleFactor:2});
  await p.goto('https://fieldsestate.com.au/off-market/11-promenade-avenue-robina'+anchor,{waitUntil:'domcontentloaded', timeout:45000});
  await new Promise(r=>setTimeout(r,5000));
  const res = await p.evaluate((a)=>{
    const el=document.querySelector(a);
    if(!el) return {found:false};
    const r=el.getBoundingClientRect();
    return {found:true, scrollY:Math.round(window.scrollY), sectionTopViewport:Math.round(r.top), inView: r.top>-50 && r.top<window.innerHeight};
  }, anchor);
  console.log(anchor, JSON.stringify(res));
  await p.close();
}
await b.close();
