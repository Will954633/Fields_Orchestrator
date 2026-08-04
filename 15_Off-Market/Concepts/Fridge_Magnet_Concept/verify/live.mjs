import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const URL='https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/index.html';
const b = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-dev-shm-usage']});

for (const [name, reduce] of [['live', false], ['reduced', true]]) {
  const p = await b.newPage();
  await p.setViewport({width:390,height:844,deviceScaleFactor:2});
  if (reduce) await p.emulateMediaFeatures([{name:'prefers-reduced-motion',value:'reduce'}]);
  const ev=[]; p.on('console',m=>ev.push(m.text()));
  await p.goto(URL+'?debug=1',{waitUntil:'networkidle0'});
  await new Promise(r=>setTimeout(r,3200));
  const open = await p.evaluate(()=>({
    isOpen: document.getElementById('fridge').classList.contains('is-open'),
    angle: getComputedStyle(document.querySelector('.door')).transform,
    topShelfOpacity: +getComputedStyle(document.querySelector('.shelf')).opacity,
  }));
  await p.screenshot({path:`verify/${name}_3s.png`});
  console.log(name, JSON.stringify(open), '| events:', ev.join(' ; ')||'none');
  await p.close();
}
await b.close();
