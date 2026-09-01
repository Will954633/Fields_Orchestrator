import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});
const p = await b.newPage();
await p.setViewport({width:390,height:844,deviceScaleFactor:2});
const hits=[]; const resp=[];
p.on('request',r=>{ if(/fridge-event/.test(r.url())) hits.push(r.method()+' '+r.url()); });
p.on('response',r=>{ if(/fridge-event/.test(r.url())) resp.push(r.status()); });
p.on('console',m=>{ if(/fridge|beacon|Event/i.test(m.text())) console.log('PAGE>',m.text()); });
await p.goto('https://fieldsestate.com.au/fridge?debug=1&sound=0',{waitUntil:'domcontentloaded'});
await new Promise(r=>setTimeout(r,1500));
const diag = await p.evaluate(()=>{
  let dt=null, err=null, sb=null;
  try{ dt=localStorage.getItem('fields_device_token'); }catch(e){ err=String(e); }
  sb = typeof navigator.sendBeacon;
  // manually invoke a fetch to the endpoint to prove reachability from page ctx
  return {device_token:dt, ls_err:err, sendBeacon:sb, hasPosthog: typeof window.posthog};
});
console.log('DIAG', JSON.stringify(diag));
await new Promise(r=>setTimeout(r,500));
console.log('fridge-event requests:', hits.length, hits);
console.log('fridge-event responses:', resp);
console.log('DEVICE_TOKEN='+diag.device_token);
await b.close();
