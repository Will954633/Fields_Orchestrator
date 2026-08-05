import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');
const URL = 'https://vm.fieldsestate.com.au/concepts/off-market/Fridge_Magnet_Concept/index.html';
const b = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb'] });
const p = await b.newPage();
await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
const errs = []; p.on('console', m => m.type()==='error' && errs.push(m.text())); p.on('pageerror', e => errs.push(String(e)));
await p.goto(URL, { waitUntil: 'networkidle0' });
// freeze the swing at chosen --open values so geometry is inspectable
for (const o of [0, 0.085, 0.35, 0.62, 1]) {
  await p.evaluate((v) => {
    const f = document.getElementById('fridge');
    f.classList.remove('is-open','is-closing');
    // kill the transition or setting --open just animates toward it and the
    // 120ms settle captures a frame from the middle of a 1.02s ease
    f.style.transition = 'none';
    f.style.setProperty('--open', v);
    document.querySelector('.flick').style.animation = 'none';
    document.querySelector('.flick').style.opacity = v < 0.15 ? '1' : '0';
    document.querySelector('.prompt').style.opacity = v === 0 ? '1' : '0';
  }, o);
  await new Promise(r => setTimeout(r, 120));
  await p.screenshot({ path: `verify/open_${String(o).replace('.','_')}.png` });
}
// overflow + link presence
const audit = await p.evaluate(() => ({
  overflowX: document.documentElement.scrollWidth > window.innerWidth,
  links: [...document.querySelectorAll('.shelf a')].map(a => a.getAttribute('href')),
}));
console.log(JSON.stringify(audit, null, 1));
console.log('console errors:', errs.length ? errs : 'none');
await b.close();
