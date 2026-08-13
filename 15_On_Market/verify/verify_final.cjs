const puppeteer=require('puppeteer');
const URL='https://fieldsestate.com.au/property/1-dandenong-terrace-robina';
async function run(arm){
  const b=await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-setuid-sandbox']});
  const p=await b.newPage();
  await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1');
  await p.setViewport({width:390,height:844,isMobile:true});
  await p.evaluateOnNewDocument(()=>Object.defineProperty(navigator,'webdriver',{get:()=>false}));
  await p.goto(URL,{waitUntil:'networkidle2',timeout:60000});
  await p.evaluate(a=>window.posthog?.featureFlags?.override({property_page_v2:a}),arm);
  // reload = the page under test; treat everything before this as setup noise
  await p.goto(URL+'?cb='+Date.now(),{waitUntil:'networkidle2',timeout:60000});
  await new Promise(r=>setTimeout(r,2500));
  const did=await p.evaluate(()=>window.posthog?.get_distinct_id?.());
  const flag=await p.evaluate(()=>window.posthog?.getFeatureFlag?.('property_page_v2'));
  // read like a person: pause on the way down so sections accrue dwell
  const h=await p.evaluate(()=>document.body.scrollHeight);
  for(let y=0;y<h;y+=400){ await p.evaluate(v=>window.scrollTo(0,v),y); await new Promise(r=>setTimeout(r,600)); }
  await new Promise(r=>setTimeout(r,2000));
  await p.evaluate(()=>{Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});document.dispatchEvent(new Event('visibilitychange'));});
  await new Promise(r=>setTimeout(r,3000));
  console.log(`${arm}\t${flag}\t${did}\tpageHeight=${h}`);
  await b.close();
}
(async()=>{ console.log('arm\tflag\tdistinct_id\theight'); await run('v2'); await run('control'); })();
