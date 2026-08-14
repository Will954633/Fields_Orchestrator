const puppeteer = require('/home/fields/Feilds_Website/01_Website/node_modules/puppeteer-core');
const OUT = '/home/fields/Fields_Orchestrator/11_House_Mini_Site/mailer/assets';
const URL = 'https://fieldsestate.com.au/your-home/25-huntingdale-crescent-robina';
const sleep = ms => new Promise(r=>setTimeout(r,ms));
(async () => {
  const b = await puppeteer.launch({ executablePath:'/usr/bin/google-chrome', headless:'new',
    args:['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-gpu','--hide-scrollbars'],
    defaultViewport:{width:1366,height:6400,deviceScaleFactor:2} });
  const p = await b.newPage();
  await p.goto(URL,{waitUntil:'networkidle2',timeout:90000});
  await sleep(2500);
  await p.evaluate(() => { const t=[...document.querySelectorAll('button,a,[role=tab]')].find(e=>/\bvaluation\b/i.test(e.textContent||'')); if(t) t.click(); });
  await sleep(3500);
  await p.evaluate(()=>window.scrollTo(0,0)); await sleep(500);
  const m = await p.evaluate(() => {
    const H=[...document.querySelectorAll('h1,h2,h3')];
    const h=H.find(e=>/derived, not declared/i.test(e.textContent||''));
    const nxt=H.find(e=>/Where these sales sit/i.test(e.textContent||''));
    const hr=h.getBoundingClientRect();
    // include the VALUATION eyebrow just above (~34px up)
    return { top: Math.round(hr.top)-58, next: Math.round(nxt.getBoundingClientRect().top) };
  });
  const bottom = m.next - 34;
  const clip = {x:56, y:Math.max(0,m.top), width:1366-112, height:bottom-Math.max(0,m.top)};
  console.log('clip:', JSON.stringify(clip));
  await p.screenshot({ path: OUT+'/val_method.png', clip });
  console.log('saved');
  await b.close();
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
