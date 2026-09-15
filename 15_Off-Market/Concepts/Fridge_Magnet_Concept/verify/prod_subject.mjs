import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');

const BASE = 'https://fieldsestate.com.au/fridge';
const b = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb'] });

async function shot(query, name) {
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  await p.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]);
  const errs = [];
  p.on('console', m => m.type()==='error' && errs.push(m.text()));
  p.on('pageerror', e => errs.push(String(e)));
  await p.goto(BASE + query, { waitUntil: 'networkidle0' });
  await p.evaluate(() => {
    const f = document.getElementById('fridge');
    if (!f) return;
    f.classList.remove('is-open','is-closing');
    f.style.transition = 'none';
    f.style.setProperty('--open', 1);
    const flick = document.querySelector('.flick'); if (flick){ flick.style.animation='none'; flick.style.opacity='0'; }
    const pr = document.querySelector('.prompt'); if (pr) pr.style.opacity='0';
  });
  await new Promise(r => setTimeout(r, 600));
  await p.screenshot({ path: `verify/${name}.png` });
  const audit = await p.evaluate(() => ({
    visibleShelves: [...document.querySelectorAll('.shelf')].filter(li => !li.hidden)
      .map(li => { const a=li.querySelector('a'); const lbl=li.querySelector('.label'); return {
        label: lbl ? lbl.childNodes[0].nodeValue.trim() : null,
        href: a ? a.getAttribute('href') : null }; }),
    bodyIsSubject: document.body.classList.contains('is-subject'),
    overflowX: document.documentElement.scrollWidth > window.innerWidth,
  }));
  console.log(`\n=== ${name} (${query||'no query — GENERIC magnet path'}) ===`);
  console.log(JSON.stringify(audit, null, 1));
  console.log('console errors:', errs.length ? errs.slice(0,4) : 'none');
  await p.close();
}

await shot('', 'prod_generic');                                 // the already-posted magnets
await shot('?slug=25-huntingdale-crescent-robina', 'prod_subject_robina');
await b.close();
