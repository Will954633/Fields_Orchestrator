import { createRequire } from 'module';
const require = createRequire('/home/fields/Feilds_Website/01_Website/package.json');
const puppeteer = require('puppeteer');

const BASE = 'file:///home/fields/Fields_Orchestrator/15_Off-Market/Concepts/Fridge_Magnet_Concept/index.html';
const b = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox','--disable-dev-shm-usage','--force-color-profile=srgb'] });

async function shot(query, name) {
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
  const errs = [];
  p.on('console', m => m.type()==='error' && errs.push(m.text()));
  p.on('pageerror', e => errs.push(String(e)));
  await p.goto(BASE + query, { waitUntil: 'networkidle0' });
  // force the door fully open so the shelves are visible for the proof
  await p.evaluate(() => {
    const f = document.getElementById('fridge');
    f.classList.remove('is-open','is-closing');
    f.style.transition = 'none';
    f.style.setProperty('--open', 1);
    const flick = document.querySelector('.flick'); if (flick){ flick.style.animation='none'; flick.style.opacity='0'; }
    const pr = document.querySelector('.prompt'); if (pr) pr.style.opacity='0';
  });
  await new Promise(r => setTimeout(r, 400)); // let poster image load
  await p.screenshot({ path: `verify/${name}.png` });
  const audit = await p.evaluate(() => ({
    visibleShelves: [...document.querySelectorAll('.shelf')].filter(li => !li.hidden)
      .map(li => { const a=li.querySelector('a'); const lbl=li.querySelector('.label'); return {
        label: lbl ? lbl.childNodes[0].nodeValue.trim() : null,
        href: a ? a.getAttribute('href') : null }; }),
    bodyIsSubject: document.body.classList.contains('is-subject'),
    overflowX: document.documentElement.scrollWidth > window.innerWidth,
  }));
  console.log(`\n=== ${name} (${query||'no query'}) ===`);
  console.log(JSON.stringify(audit, null, 1));
  console.log('console errors:', errs.length ? errs : 'none');
  await p.close();
}

await shot('?slug=25-huntingdale-crescent-robina', 'subject_robina');
await shot('?slug=1-bluejay-street-burleigh-waters', 'subject_burleigh');
await shot('', 'generic_no_slug');   // control: the already-distributed generic magnet path
await b.close();
